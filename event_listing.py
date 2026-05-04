"""
event_listing.py — Tickethouse.net Bot
=========================================
Reads event metadata from event_data.db (populated by event_scraper.py)
and creates new events on tickethouse.net for any that don't yet exist.

Each event is created with the standard sections for that team.

Run once (or on a schedule): python3 event_listing.py
"""

import sqlite3
import requests
import json
import time
import traceback

from config import BASE_URL, USER_ID

STATUS_FILE = 'status.txt'

# ─── Sections per team ────────────────────────────────────────────────────────
# Each entry: {'name': str, 'color': str}
TEAM_SECTIONS = {
    'Arsenal': [
        {'name': 'VIP Club Level',  'color': '#FF0000'},
    ],
    'Chelsea': [
        {'name': 'VIP Packages',         'color': '#034694'},
        {'name': 'Longside Lower Tier',  'color': '#034694'},
    ],
    'Crystal Palace': [
        {'name': 'VIP Packages',  'color': '#1B458F'},
        {'name': 'Longside Tier', 'color': '#1B458F'},
    ],
    'Fulham': [
        {'name': 'Shortside Tier',       'color': '#CC0000'},
        {'name': 'Longside Upper Tier',  'color': '#CC0000'},
        {'name': 'VIP Packages',         'color': '#CC0000'},
    ],
    'Liverpool': [
        {'name': 'VIP Packages', 'color': '#C8102E'},
    ],
    'Manchester City': [
        {'name': 'VIP Packages', 'color': '#6CABDD'},
    ],
    'Manchester United': [
        {'name': 'VIP Packages', 'color': '#DA291C'},
    ],
    'Tottenham Hotspur': [
        {'name': 'Shortside Upper Tier', 'color': '#132257'},
        {'name': 'Longside Upper Tier',  'color': '#132257'},
        {'name': 'VIP Packages',         'color': '#132257'},
    ],
    'Aston Villa': [
        {'name': 'Longside Upper',  'color': '#95BFE5'},
        {'name': 'Shortside Upper', 'color': '#95BFE5'},
        {'name': 'VIP Packages',    'color': '#95BFE5'},
    ],
    'Brentford': [
        {'name': 'Longside Upper', 'color': '#E30613'},
        {'name': 'VIP Packages',   'color': '#E30613'},
    ],
    'Leeds United': [
        {'name': 'VIP Packages', 'color': '#FFCD00'},
    ],
    'Atletico Madrid': [
        {'name': 'VIP Hospitality', 'color': '#CB3524'},
    ],
    'Sevilla FC': [
        {'name': 'VIP Hospitality',       'color': '#D4001A'},
        {'name': 'Lateral Tribuna Alto N43', 'color': '#D4001A'},
        {'name': 'Gol Tribuna Alto N46',  'color': '#D4001A'},
    ],
}


# ─── API helpers ─────────────────────────────────────────────────────────────
def get_existing_events() -> set:
    """Return a set of (event_name, event_date) already on the website."""
    headers = {'Authorization': f'Token {USER_ID}'}
    existing = set()
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
        for e in data.get('events', []):
            existing.add((e['name'], e['date']))
        if page >= data.get('total_pages', 1):
            break
        page += 1
    print(f'Found {len(existing)} existing events on tickethouse.net')
    return existing


def create_event(event_name: str, event_date: str, event_time: str,
                 stadium_name: str, stadium_image: str, event_logo: str,
                 sections: list) -> str | None:
    """Create a new event on tickethouse.net. Returns the new event_id or None."""
    headers = {'Authorization': f'Token {USER_ID}', 'Content-Type': 'application/json'}
    payload = {
        'name':          event_name,
        'category':      'sports',
        'date':          event_date,
        'time':          event_time or '00:00:00',
        'stadium_name':  stadium_name or 'TBD',
        'stadium_image': stadium_image or '',
        'event_logo':    event_logo or '',
        'sections':      sections,
    }
    resp = requests.post(
        f'{BASE_URL}/api/events/create/',
        headers=headers,
        data=json.dumps(payload),
        timeout=20
    )
    print(f'  Create event "{event_name}" ({event_date}): {resp.status_code} — {resp.text[:120]}')
    if resp.status_code in (200, 201):
        return resp.json().get('event_id')
    return None


# ─── Data loading ─────────────────────────────────────────────────────────────
def load_from_event_db() -> list:
    """Load all events from event_data.db."""
    conn = sqlite3.connect('event_data.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT event_name, event_date, event_time, stadium_name, stadium_image, event_logo FROM events'
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            'event_name':    r[0],
            'event_date':    r[1],
            'event_time':    r[2],
            'stadium_name':  r[3],
            'stadium_image': r[4],
            'event_logo':    r[5],
        }
        for r in rows
    ]


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print('=== Event Listing Bot Starting ===')

    events_from_db = load_from_event_db()
    print(f'Loaded {len(events_from_db)} events from event_data.db')

    existing = get_existing_events()

    created = 0
    skipped = 0

    for ev in events_from_db:
        event_name = ev['event_name']
        event_date = ev['event_date']

        if (event_name, event_date) in existing:
            skipped += 1
            continue

        # Determine home team from event name
        home_team = event_name.split(' v ')[0].strip()
        sections = TEAM_SECTIONS.get(home_team)
        if not sections:
            print(f'  No sections defined for team: {home_team} — skipping.')
            skipped += 1
            continue

        event_id = create_event(
            event_name=event_name,
            event_date=event_date,
            event_time=ev['event_time'],
            stadium_name=ev['stadium_name'],
            stadium_image=ev['stadium_image'],
            event_logo=ev['event_logo'],
            sections=sections,
        )
        if event_id:
            created += 1
        time.sleep(1)

    print(f'\n=== Done. Created: {created}, Skipped: {skipped} ===')
