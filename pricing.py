"""
pricing.py — Tickethouse.net Bot
==================================
Dynamically updates sell prices for active listings based on:
  - Competitor prices in the same section
  - Time remaining until the event (profit margin tiers)
  - Never prices below face value

Run continuously: python3 pricing.py
"""

import sqlite3
import time
import requests
import json
import traceback
import copy
from datetime import datetime, timedelta

from config import (
    BASE_URL, USER_ID, SKIP_TEAMS, DECODING_DICT,
    PROFIT_RANGES, LISTING_ROW, LISTING_TICKET_TYPE,
    LISTING_UPLOAD_CHOICE
)

STATUS_FILE = 'status.txt'


# ─── Helpers ─────────────────────────────────────────────────────────────────
def wait_for_scraper():
    try:
        with open(STATUS_FILE) as f:
            status = f.read().strip()
    except FileNotFoundError:
        return
    while status != 'break':
        print('Scraper updating — waiting...')
        time.sleep(3)
        try:
            with open(STATUS_FILE) as f:
                status = f.read().strip()
        except FileNotFoundError:
            break


def normalise_name(raw: str) -> str:
    for old, new in [('&', 'and'), ('é', 'e'), ('ü', 'u'), ('ó', 'o'), ('á', 'a')]:
        raw = raw.replace(old, new)
    return raw


def days_until(date_str: str) -> int:
    event_date = datetime.strptime(date_str, '%Y-%m-%d')
    return (event_date - datetime.now()).days


def get_profit_multiplier(date_str: str) -> float:
    days = days_until(date_str)
    for threshold, multiplier in PROFIT_RANGES:
        if days <= threshold:
            return multiplier
    return 1.40


# ─── Price calculation ────────────────────────────────────────────────────────
def calculate_optimal_price(event_id: str, section_id: int, face_value: float,
                             number_of_tickets: int, event_date: str) -> float:
    """
    Fetch all competitor listings in the same section with the same quantity,
    then price just below the cheapest competitor above our minimum profit price.
    Never go below face value.
    """
    headers = {'Authorization': f'Token {USER_ID}'}
    multiplier = get_profit_multiplier(event_date)
    min_price = round(float(face_value) * multiplier, 2)

    try:
        resp = requests.get(
            f'{BASE_URL}/api/events/{event_id}/tickets/',
            headers=headers,
            params={
                'section': section_id,
                'number_of_tickets': number_of_tickets,
                'per_page': 100,
            },
            timeout=20
        )
        if resp.status_code != 200:
            return min_price

        tickets = resp.json().get('tickets', [])
        price = min_price

        for ticket in sorted(tickets, key=lambda t: float(t.get('price_per_ticket', 0))):
            if ticket.get('row') == LISTING_ROW:
                continue  # skip our own bot listings
            competitor_price = float(ticket.get('price_per_ticket', 0))
            if competitor_price > min_price:
                price = competitor_price - 1
                break

        # Never price below face value
        price = max(price, float(face_value))
        return round(price, 2)

    except Exception:
        traceback.print_exc()
        return min_price


# ─── Ticket update ────────────────────────────────────────────────────────────
def update_ticket_price(ticket_id: str, ticket_data: dict):
    """PATCH a single ticket's sell_price via the API."""
    headers = {'Authorization': f'Token {USER_ID}', 'Content-Type': 'application/json'}
    url = f'{BASE_URL}/api/tickets/update/{ticket_id}/'

    payload = {
        'upload_choice':           LISTING_UPLOAD_CHOICE,
        'upload_by':               ticket_data['upload_by'],
        'number_of_tickets':       ticket_data['number_of_tickets'],
        'section':                 ticket_data['section_id'],
        'row':                     ticket_data['row'],
        'seats':                   ticket_data['seats'],
        'face_value':              round(float(ticket_data['face_value']), 2),
        'ticket_type':             LISTING_TICKET_TYPE,
        'benefits_and_Restrictions': [],
        'sell_price':              round(float(ticket_data['sell_price']), 2),
        'sell_together':           False,
    }

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
    print(f'  Update {ticket_id}: {resp.status_code} — {resp.text[:120]}')


# ─── Data loading ─────────────────────────────────────────────────────────────
def load_from_db() -> dict:
    """
    Returns a dict keyed by 'event_name_date_section' with price and quantities.
    """
    wait_for_scraper()

    conn = sqlite3.connect('ticket_data.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT home, away, date, ticket_name, quantity, ticket_price FROM events'
    )
    rows = cursor.fetchall()
    conn.close()

    unique = {}
    for home, away, date, ticket_name, qty, price in rows:
        if home in SKIP_TEAMS:
            continue
        if home == 'Atletico Madrid' and ticket_name != 'VIP Club East/East Club':
            continue
        if 'Women' in away:
            continue

        decode = DECODING_DICT.get(home)
        if not decode or ticket_name not in decode:
            continue

        section_name = decode[ticket_name]
        event_name = normalise_name(f'{home} v {away}')
        key = f'{event_name}_{date}_{section_name}'

        qty_list = [i + 1 for i in range(min(qty, 6))]
        new = {'ticket_price': price, 'quantities': qty_list}

        if key not in unique:
            unique[key] = new
        else:
            existing = unique[key]
            if qty >= 6:
                if price < existing['ticket_price']:
                    unique[key] = new
            else:
                if len(qty_list) > len(existing['quantities']):
                    unique[key] = new
                elif len(qty_list) == len(existing['quantities']) and price < existing['ticket_price']:
                    unique[key] = new

    return unique


# ─── Main pricing loop ────────────────────────────────────────────────────────
def run_pricing_cycle(tc_data: dict):
    """
    Fetch all active listings, compare current price vs optimal price,
    and update any that differ.
    """
    headers = {'Authorization': f'Token {USER_ID}'}
    to_update = {}

    page = 1
    while True:
        resp = requests.get(
            f'{BASE_URL}/api/tickets/my-listings/',
            headers=headers,
            params={'status': 'active', 'page': page, 'per_page': 100},
            timeout=20
        )
        if resp.status_code != 200:
            print(f'My-listings error: {resp.status_code}')
            break

        data = resp.json()
        tickets = data.get('tickets', [])

        for ticket in tickets:
            event = ticket['event']
            key = f"{event['name']}_{event['date']}_{ticket['section']}"

            if key not in tc_data:
                continue  # Not a TC-sourced listing — skip

            face_value = float(ticket['face_value'])
            optimal = calculate_optimal_price(
                event_id=event['event_id'],
                section_id=ticket['section_id'],
                face_value=face_value,
                number_of_tickets=ticket['number_of_tickets'],
                event_date=event['date'],
            )

            current_price = float(ticket['sell_price'])
            if abs(optimal - current_price) < 0.01:
                continue  # No change needed

            print(f"  Price change: {event['name']} | {ticket['section']} | "
                  f"qty={ticket['number_of_tickets']} | "
                  f"{current_price} → {optimal}")

            # Clean seats string
            cleaned_seats = [s.strip().strip("[]'\"") for s in ticket['seats']]
            seats_str = ', '.join(cleaned_seats)

            to_update[ticket['ticket_id']] = {
                'upload_by':       ticket.get('upload_by', ''),
                'number_of_tickets': ticket['number_of_tickets'],
                'section_id':      ticket['section_id'],
                'row':             ticket['row'],
                'seats':           seats_str,
                'face_value':      face_value,
                'sell_price':      optimal,
            }

        if page >= data.get('total_pages', 1):
            break
        page += 1

    print(f'Updating {len(to_update)} tickets...')
    for ticket_id, tdata in to_update.items():
        update_ticket_price(ticket_id, tdata)
        time.sleep(1)


# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    while True:
        try:
            print('=== Pricing Bot Cycle Starting ===')
            tc_data = load_from_db()
            run_pricing_cycle(tc_data)
            print('Pricing cycle complete. Sleeping 100 seconds...\n')
            time.sleep(100)
        except Exception:
            traceback.print_exc()
            print('Error — retrying in 30 seconds...')
            time.sleep(30)
