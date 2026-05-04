"""
event_listing.py — Tickethouse.net Bot
=========================================
Reads event metadata from event_data.db (populated by event_scraper.py)
and creates new events on tickethouse.net for any that don't yet exist.

Each event is created with:
  - Correct stadium name and SVG key for the home team
  - Category: 'football' (shows under Football tab)
  - Service charges: 5% normal users, 3% resellers
  - Sections defined per home team

Run once (or on a schedule): python3 event_listing.py
"""

import sqlite3
import requests
import json
import time
import traceback
from datetime import datetime, date

from config import BASE_URL, SUPERADMIN_USER_ID

# Default placeholder images used when event_scraper.py did not find images
DEFAULT_STADIUM_IMAGE = 'https://tickethouse.net/static/events/img/default_stadium.jpg'
DEFAULT_EVENT_LOGO    = 'https://tickethouse.net/static/events/img/default_logo.png'

# Service charges (percentage)
NORMAL_SERVICE_CHARGE   = 5   # 5% for normal users
RESELLER_SERVICE_CHARGE = 3   # 3% for resellers

# ─── Team → Stadium mapping ───────────────────────────────────────────────────
# Keys must match the STADIUM_SVG_CHOICES in events/models.py exactly
TEAM_STADIUM = {
    'Arsenal':           {'name': 'Emirates Stadium',           'svg_key': 'emiratesStadium'},
    'Aston Villa':       {'name': 'Villa Park Stadium',         'svg_key': 'villaParkStadium'},
    'Manchester United': {'name': 'Old Trafford',               'svg_key': 'oldTraffordStadium'},
    'Liverpool':         {'name': 'Anfield Stadium',            'svg_key': 'anfieldStadium'},
    'Leeds United':      {'name': 'Elland Road',                'svg_key': 'ellandStadium'},
    'Tottenham Hotspur': {'name': 'Tottenham Hotspur Stadium',  'svg_key': 'tottenhamHotspurStadium'},
    'Chelsea':           {'name': 'Stamford Bridge',            'svg_key': 'stamfordBridge'},
    'Manchester City':   {'name': 'Etihad Stadium',             'svg_key': 'etihadStadium'},
    'Fulham':            {'name': 'Craven Cottage',             'svg_key': 'cravenCottage'},
    'Crystal Palace':    {'name': 'Selhurst Park',              'svg_key': 'selhurstPark'},
    'Brentford':         {'name': 'Gtech Community Stadium',    'svg_key': 'gtechCommunityStadium'},
    'Atletico Madrid':   {'name': 'Riyadh Metropolitano Stadium', 'svg_key': 'riyadhMetropolitanoStadium'},
    'Sevilla FC':        {'name': 'Estadio Ramon Sanchez Pizjuan', 'svg_key': None},
    'Real Sociedad':     {'name': 'Reale Arena',                'svg_key': None},
    'Nottingham Forest': {'name': 'City Ground',                'svg_key': None},
    'AFC Bournemouth':   {'name': 'Vitality Stadium',           'svg_key': None},
}

# ─── Sections per team ────────────────────────────────────────────────────────
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
        {'name': 'VIP Hospitality',          'color': '#D4001A'},
        {'name': 'Lateral Tribuna Alto N43', 'color': '#D4001A'},
        {'name': 'Gol Tribuna Alto N46',     'color': '#D4001A'},
    ],
}


# ─── API helpers ─────────────────────────────────────────────────────────────
def get_existing_events() -> set:
    """Return a set of (event_name, event_date) already on the website."""
    headers = {'Authorization': f'Token {SUPERADMIN_USER_ID}'}
    existing = set()
    page = 1
    while True:
        resp = requests.get(
            f'{BASE_URL}/api/events/all/',
            headers=headers,
            params={'page': page, 'per_page': 100, 'sort': 'all'},
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
                 stadium_name: str, stadium_svg_key: str | None,
                 stadium_image: str, event_logo: str,
                 sections: list) -> str | None:
    """Create a new event on tickethouse.net. Returns the new event_id or None."""
    headers = {'Authorization': f'Token {SUPERADMIN_USER_ID}', 'Content-Type': 'application/json'}
    payload = {
        'name':                    event_name,
        'category':                'football',
        'date':                    event_date,
        'time':                    event_time or '15:00:00',
        'stadium_name':            stadium_name or 'TBD',
        'stadium_svg_key':         stadium_svg_key,
        'stadium_image':           stadium_image or DEFAULT_STADIUM_IMAGE,
        'event_logo':              event_logo or DEFAULT_EVENT_LOGO,
        'sections':                sections,
        'normal_service_charge':   NORMAL_SERVICE_CHARGE,
        'reseller_service_charge': RESELLER_SERVICE_CHARGE,
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

    today = date.today()

    for ev in events_from_db:
        event_name = ev['event_name']
        event_date = ev['event_date']

        # Skip past events — the API rejects them
        try:
            ev_date = datetime.strptime(event_date, '%Y-%m-%d').date()
            if ev_date < today:
                skipped += 1
                continue
        except (ValueError, TypeError):
            pass

        if (event_name, event_date) in existing:
            skipped += 1
            continue

        # Determine home team from event name
        home_team = event_name.split(' v ')[0].strip()

        # Get sections for this home team
        sections = TEAM_SECTIONS.get(home_team)
        if not sections:
            print(f'  No sections defined for team: {home_team} — skipping.')
            skipped += 1
            continue

        # Get stadium info for this home team
        stadium_info = TEAM_STADIUM.get(home_team, {})
        # Use scraped stadium_name if available, otherwise use mapped name
        stadium_name = ev['stadium_name'] if ev['stadium_name'] and ev['stadium_name'] != 'TBD' \
                       else stadium_info.get('name', 'TBD')
        stadium_svg_key = stadium_info.get('svg_key')

        event_id = create_event(
            event_name=event_name,
            event_date=event_date,
            event_time=ev['event_time'],
            stadium_name=stadium_name,
            stadium_svg_key=stadium_svg_key,
            stadium_image=ev['stadium_image'],
            event_logo=ev['event_logo'],
            sections=sections,
        )
        if event_id:
            created += 1
        time.sleep(1)

    print(f'\n=== Done. Created: {created}, Skipped: {skipped} ===')
