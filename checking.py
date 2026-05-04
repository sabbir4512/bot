"""
checking.py — Tickethouse.net Bot
===================================
Verifies that all expected listings exist on tickethouse.net.
For any event/section/quantity combination that is missing a listing,
it creates a new one (re-listing).

Run continuously: python3 checking.py
"""

import sqlite3
import time
import requests
import json
import traceback
from datetime import datetime, timedelta

from config import (
    BASE_URL, USER_ID, SKIP_TEAMS, DECODING_DICT,
    LISTING_ROW, LISTING_TICKET_TYPE, LISTING_UPLOAD_CHOICE,
    CHECKING_STARTING_SEAT
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


# ─── API helpers ─────────────────────────────────────────────────────────────
def get_all_events():
    headers = {'Authorization': f'Token {USER_ID}'}
    events = []
    page = 1
    while True:
        resp = requests.get(
            f'{BASE_URL}/api/events/all/',
            headers=headers,
            params={'page': page, 'per_page': 100},
            timeout=20
        )
        if resp.status_code != 200:
            print(f'Events API error: {resp.status_code}')
            break
        data = resp.json()
        events.extend(data.get('events', []))
        if page >= data.get('total_pages', 1):
            break
        page += 1
    return events


def get_my_listings():
    """Return all active listings as a list of ticket dicts."""
    headers = {'Authorization': f'Token {USER_ID}'}
    listings = []
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
        listings.extend(data.get('tickets', []))
        if page >= data.get('total_pages', 1):
            break
        page += 1
    return listings


def get_section_id(event_id: str, section_name: str) -> int | None:
    """Look up the section ID using the robust api_helpers method."""
    from api_helpers import get_section_id as _get_section_id
    return _get_section_id(event_id, section_name)


def create_listing(event_id: str, event_date: str, section_id: int,
                   qty: int, face_value: float, sell_price: float,
                   starting_seat: int = CHECKING_STARTING_SEAT):
    headers = {'Authorization': f'Token {USER_ID}', 'Content-Type': 'application/json'}
    url = f'{BASE_URL}/api/events/{event_id}/create-listing/'

    date_obj = datetime.strptime(event_date, '%Y-%m-%d')
    upload_by = (date_obj - timedelta(days=1)).strftime('%Y-%m-%d')

    seats_str = ', '.join(str(starting_seat + i) for i in range(qty))
    payload = {
        'upload_choice':           LISTING_UPLOAD_CHOICE,
        'upload_file':             '',
        'upload_by':               upload_by,
        'number_of_tickets':       qty,
        'section':                 section_id,
        'row':                     LISTING_ROW,
        'seats':                   seats_str,
        'face_value':              round(face_value, 2),
        'ticket_type':             LISTING_TICKET_TYPE,
        'benefits_and_Restrictions': [],
        'sell_price':              round(sell_price, 2),
        'sell_together':           False,
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=20)
    print(f'  Re-list qty={qty}: {resp.status_code} — {resp.text[:120]}')
    return resp.status_code in (200, 201)


# ─── Data loading ─────────────────────────────────────────────────────────────
def load_from_db() -> dict:
    """
    Returns a dict keyed by (event_name, date, section_name) with
    {'ticket_price': float, 'quantities': list[int]}.
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
        key = (event_name, date, section_name)

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


# ─── Main checking loop ───────────────────────────────────────────────────────
def run_checking_cycle():
    print('=== Checking Bot Cycle Starting ===')

    tc_data = load_from_db()
    all_events = get_all_events()
    my_listings = get_my_listings()

    # Build lookup: (event_name, event_date) → event_id
    event_lookup = {(e['name'], e['date']): e['event_id'] for e in all_events}

    # Build set of (event_id, section_name, qty) already listed
    already_listed = set()
    for ticket in my_listings:
        event = ticket['event']
        already_listed.add((event['event_id'], ticket['section'], ticket['number_of_tickets']))

    relisted = 0
    skipped = 0

    for (event_name, date, section_name), info in tc_data.items():
        event_id = event_lookup.get((event_name, date))
        if event_id is None:
            skipped += 1
            continue

        face_value = round(float(info['ticket_price']), 2)
        sell_price = round(face_value + 200, 2)

        for qty in info['quantities']:
            if (event_id, section_name, qty) in already_listed:
                continue

            print(f"\nMissing listing: {event_name} | {date} | {section_name} | qty={qty}")
            section_id = get_section_id(event_id, section_name)
            if section_id is None:
                print(f"  Section '{section_name}' not found — skipping.")
                continue

            ok = create_listing(
                event_id=event_id,
                event_date=date,
                section_id=section_id,
                qty=qty,
                face_value=face_value,
                sell_price=sell_price,
            )
            if ok:
                relisted += 1
            time.sleep(1)

    print(f'=== Checking Done. Re-listed: {relisted}, Skipped: {skipped} ===\n')


# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    while True:
        try:
            run_checking_cycle()
            print('Sleeping 5 minutes...')
            time.sleep(300)
        except Exception:
            traceback.print_exc()
            print('Error — retrying in 30 seconds...')
            time.sleep(30)
