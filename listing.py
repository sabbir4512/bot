"""
listing.py — Tickethouse.net Bot
==================================
Reads from ticket_data.db (populated by scraper.py) and creates new
listings on tickethouse.net for events that don't yet have any listing.

Run once (or on a schedule): python3 listing.py
"""

import sqlite3
import time
import requests
import json
import traceback
from datetime import datetime, timedelta

from config import (
    BASE_URL, USER_ID, HOME_TEAMS, SKIP_TEAMS,
    DECODING_DICT, LISTING_ROW, LISTING_TICKET_TYPE,
    LISTING_UPLOAD_CHOICE, LISTING_STARTING_SEAT
)

STATUS_FILE = 'status.txt'


# ─── Helpers ─────────────────────────────────────────────────────────────────
def wait_for_scraper():
    """Block until scraper.py has finished its current update cycle."""
    try:
        with open(STATUS_FILE) as f:
            status = f.read().strip()
    except FileNotFoundError:
        return  # No status file — proceed anyway

    while status != 'break':
        print('Scraper is still updating — waiting...')
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


def get_all_events():
    """Fetch all upcoming events from tickethouse.net API."""
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
    print(f'Fetched {len(events)} events from tickethouse.net')
    return events


def get_my_listed_event_ids():
    """Return a set of event_ids that already have at least one active listing."""
    headers = {'Authorization': f'Token {USER_ID}'}
    listed = set()
    page = 1
    while True:
        resp = requests.get(
            f'{BASE_URL}/api/tickets/my-listings/',
            headers=headers,
            params={'status': 'active', 'page': page, 'per_page': 100},
            timeout=20
        )
        if resp.status_code != 200:
            print(f'My-listings API error: {resp.status_code}')
            break
        data = resp.json()
        for ticket in data.get('tickets', []):
            listed.add(ticket['event']['event_id'])
        if page >= data.get('total_pages', 1):
            break
        page += 1
    print(f'Found {len(listed)} events already listed.')
    return listed


def get_section_id(event_id: str, section_name: str) -> int | None:
    """Look up the section ID using the robust api_helpers method."""
    from api_helpers import get_section_id as _get_section_id
    return _get_section_id(event_id, section_name)


def create_listing(event_id: str, event_date: str, section_id: int,
                   quantities: list, face_value: float, sell_price: float,
                   starting_seat: int = LISTING_STARTING_SEAT):
    """Create one listing per quantity in the quantities list."""
    headers = {'Authorization': f'Token {USER_ID}', 'Content-Type': 'application/json'}
    url = f'{BASE_URL}/api/events/{event_id}/create-listing/'

    # upload_by must be the day before the event
    date_obj = datetime.strptime(event_date, '%Y-%m-%d')
    upload_by = (date_obj - timedelta(days=1)).strftime('%Y-%m-%d')

    current_seat = starting_seat
    for qty in quantities:
        seats_str = ', '.join(str(current_seat + i) for i in range(qty))
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
        print(f'  Create listing qty={qty}: {resp.status_code} — {resp.text[:120]}')
        current_seat += qty
        time.sleep(1)


# ─── Data loading ─────────────────────────────────────────────────────────────
def load_from_db() -> list:
    """
    Read ticket_data.db and return a deduplicated list of ticket dicts.
    Skips teams in SKIP_TEAMS and women's matches.
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
        new = {
            'event_name':          event_name,
            'event_date':          date,
            'section_name':        section_name,
            'ticket_quantity':     qty,
            'ticket_quantity_list': [i + 1 for i in range(min(qty, 6))],
            'ticket_price':        price,
        }

        if key not in unique:
            unique[key] = new
        else:
            existing = unique[key]
            if qty >= 6:
                if price < existing['ticket_price']:
                    unique[key] = new
            else:
                if qty > existing['ticket_quantity']:
                    unique[key] = new
                elif qty == existing['ticket_quantity'] and price < existing['ticket_price']:
                    unique[key] = new

    return list(unique.values())


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print('=== Listing Bot Starting ===')

    # Load data from Travel Connection DB
    tc_tickets = load_from_db()
    print(f'Loaded {len(tc_tickets)} unique ticket types from local DB.')

    # Fetch website data
    all_events = get_all_events()
    already_listed = get_my_listed_event_ids()

    # Build lookup: (name, date) → event_id
    event_lookup = {
        (e['name'], e['date']): e['event_id']
        for e in all_events
    }

    listed_count = 0
    skipped_count = 0

    for tc in tc_tickets:
        event_id = event_lookup.get((tc['event_name'], tc['event_date']))
        if event_id is None:
            print(f"  No website event found for: {tc['event_name']} on {tc['event_date']}")
            skipped_count += 1
            continue

        if event_id in already_listed:
            print(f"  Already listed: {tc['event_name']} ({event_id})")
            skipped_count += 1
            continue

        print(f"\nListing: {tc['event_name']} | {tc['event_date']} | {tc['section_name']}")
        section_id = get_section_id(event_id, tc['section_name'])
        if section_id is None:
            skipped_count += 1
            continue

        face_value = round(float(tc['ticket_price']), 2)
        sell_price = round(face_value + 200, 2)

        create_listing(
            event_id=event_id,
            event_date=tc['event_date'],
            section_id=section_id,
            quantities=tc['ticket_quantity_list'],
            face_value=face_value,
            sell_price=sell_price,
        )
        listed_count += 1

    print(f'\n=== Done. Listed: {listed_count}, Skipped: {skipped_count} ===')
