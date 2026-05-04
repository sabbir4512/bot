"""
scraper.py — Tickethouse.net Bot
=================================
Fetches upcoming football match tickets from the Travel Connection API
and stores them in a local SQLite database (ticket_data.db).

Run continuously: python3 scraper.py
"""

import requests
import sqlite3
from currency_changer import convert_euro_to_pound
from datetime import datetime
import time
import traceback
import os
import json

from config import (
    TC_API_URL, TC_USERNAME, TC_PASSWORD, TC_TOKEN_FILE, HOME_TEAMS
)
from event_delete import auto_cleanup_expired_events

# ─── Status file ────────────────────────────────────────────────────────────
STATUS_FILE = 'status.txt'

def update_status(status):
    with open(STATUS_FILE, 'w') as f:
        f.write(status)

# ─── Database ────────────────────────────────────────────────────────────────
def initialize_database():
    conn = sqlite3.connect('ticket_data.db')
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            home          TEXT,
            away          TEXT,
            date          TEXT,
            ticket_name   TEXT,
            ticket_price  REAL,
            quantity      INTEGER,
            scraped       TIMESTAMP,
            PRIMARY KEY (home, date, ticket_name)
        )
    """)
    conn.commit()
    return conn, cursor


def update_database(cursor, conn, home, away, date, ticket_name,
                    ticket_price, quantity, scrape_time):
    cursor.execute("""
        INSERT INTO events (home, away, date, ticket_name, ticket_price, quantity, scraped)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (home, date, ticket_name)
        DO UPDATE SET
            ticket_price = excluded.ticket_price,
            quantity     = excluded.quantity,
            scraped      = excluded.scraped
    """, (home, away, date, ticket_name, ticket_price, quantity, scrape_time))
    conn.commit()


def delete_olds(cursor, conn, current_scrape_timestamp):
    cursor.execute("DELETE FROM events WHERE scraped < ?", (current_scrape_timestamp,))
    conn.commit()


# ─── Travel Connection API ───────────────────────────────────────────────────
def get_token(username=TC_USERNAME, password=TC_PASSWORD, token_file=TC_TOKEN_FILE):
    url = f'{TC_API_URL}/oauthorize/token'
    headers = {'accept': 'application/json', 'content-type': 'application/json'}
    now = int(time.time())

    if os.path.exists(token_file):
        try:
            with open(token_file) as f:
                stored = json.load(f)
            access = stored.get('access_token')
            expires_at = int(stored.get('expires_at', 0))
            refresh = stored.get('refresh_token')
            if access and now < (expires_at - 30):
                return access
            if refresh:
                resp = requests.post(
                    url,
                    json={'grant_type': 'refresh_token', 'refresh_token': refresh},
                    headers=headers
                )
                resp.raise_for_status()
                j = resp.json()
                data = {
                    'access_token': j.get('access_token'),
                    'refresh_token': j.get('refresh_token'),
                    'expires_at': now + int(j.get('expires_in', 3600))
                }
                with open(token_file, 'w') as f:
                    json.dump(data, f)
                return data['access_token']
        except Exception:
            pass

    if not password:
        raise ValueError('No valid token and no password provided.')
    resp = requests.post(
        url,
        json={'grant_type': 'password', 'username': username, 'password': password},
        headers=headers
    )
    resp.raise_for_status()
    j = resp.json()
    data = {
        'access_token': j.get('access_token'),
        'refresh_token': j.get('refresh_token'),
        'expires_at': now + int(j.get('expires_in', 3600))
    }
    with open(token_file, 'w') as f:
        json.dump(data, f)
    return data['access_token']


def get_upcoming_products(token):
    url = f'{TC_API_URL}/product/upcoming'
    headers = {'accept': 'application/json', 'authorization': f'Bearer {token}'}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        products = []
        for item in response.json().get('data', []):
            if item.get('type') != 'football_match':
                continue
            products.append({
                'id':   item.get('id'),
                'name': item.get('name'),
                'date': item.get('date', '').split('T')[0],
            })
        return products
    except Exception:
        traceback.print_exc()
        return []


def get_product_tickets(token, products):
    """Fetch ticket availability for up to 10 products at a time."""
    url = f'{TC_API_URL}/inventory-status'
    headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
        'authorization': f'Bearer {token}'
    }
    product_ids = [p['id'] for p in products]
    try:
        resp = requests.post(url, json={'products': product_ids}, headers=headers, timeout=30)
        resp.raise_for_status()
        tickets = []
        for item in resp.json().get('data', []):
            if item.get('status') != 'Upcoming':
                continue
            pid = item.get('id')
            for ticket in item.get('ticket_options', []):
                if pid in product_ids and ticket.get('available'):
                    product = next((p for p in products if p['id'] == pid), None)
                    if product:
                        tickets.append({
                            'product_name':     product['name'],
                            'product_date':     product['date'],
                            'ticket_name':      ticket.get('name'),
                            'ticket_price':     ticket.get('price'),
                            'ticket_quantity':  ticket.get('max_purchase_qty'),
                        })
        return tickets
    except Exception:
        traceback.print_exc()
        return []


# ─── Spanish clubs that price in EUR ─────────────────────────────────────────
EURO_CLUBS = {
    'Atletico Madrid', 'FC Barcelona', 'Real Madrid',
    'Real Sociedad', 'Sevilla FC', 'RCD Mallorca', 'RCD Espanyol'
}


# ─── Main loop ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    while True:
        try:
            update_status('updating')
            print('=== Scraper starting new cycle ===')

            token = get_token()
            print(f'TC token obtained.')

            upcoming = get_upcoming_products(token)
            print(f'{len(upcoming)} upcoming products found.')

            all_tickets = []
            for i in range(0, len(upcoming), 10):
                batch = upcoming[i:i + 10]
                print(f'  Fetching tickets for products {i+1}–{min(i+10, len(upcoming))}...')
                try:
                    batch_tickets = get_product_tickets(token, batch)
                    all_tickets.extend(batch_tickets)
                except Exception:
                    pass
                time.sleep(2)

            conn, cursor = initialize_database()
            current_time = datetime.now()

            saved = 0
            for home_team in HOME_TEAMS:
                for ticket in all_tickets:
                    parts = ticket['product_name'].split(' v ')
                    if len(parts) < 2:
                        continue
                    tc_home = parts[0].strip()
                    if home_team not in tc_home:
                        continue

                    away = parts[1].strip()
                    if 'Women' in away:
                        continue

                    match_date = ticket['product_date']
                    ticket_name = ticket['ticket_name']
                    price = ticket['ticket_price']

                    # Normalise home team name
                    home = home_team
                    if home == 'Atletico Madrid':
                        home = 'Atletico Madrid'

                    # Convert EUR → GBP for Spanish clubs
                    if home in EURO_CLUBS:
                        price = convert_euro_to_pound(price)

                    # Normalise event name characters
                    event_name = f'{home} v {away}'
                    for old, new in [('&', 'and'), ('é', 'e'), ('ü', 'u'), ('ó', 'o'), ('á', 'a')]:
                        event_name = event_name.replace(old, new)

                    update_database(
                        cursor, conn,
                        home, away, match_date,
                        ticket_name, price,
                        ticket['ticket_quantity'],
                        current_time
                    )
                    saved += 1

            delete_olds(cursor, conn, current_time)
            conn.close()
            print(f'Database updated: {saved} ticket entries saved.')
            # Auto-delete any expired events from tickethouse.net
            auto_cleanup_expired_events()
            update_status('break')
            print('Taking a break (5 minutes)...\n')
            time.sleep(300)

        except Exception:
            traceback.print_exc()
            print('Error — restarting in 30 seconds...')
            time.sleep(30)
