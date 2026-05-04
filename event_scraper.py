"""
event_scraper.py — Tickethouse.net Bot
========================================
Fetches event metadata (match name, date, time, stadium images, logos)
directly from the Travel Connection API and stores them in event_data.db.

Images come from the TC API product detail endpoint:
  GET /product/{id}  →  data.images.main  (event card image)
                        data.images.thumb (thumbnail)

Run once (or on a schedule): python3 event_scraper.py
"""

import sqlite3
import requests
import time
import re

from config import TC_API_URL, HOME_TEAMS
from scraper import get_token, get_upcoming_products


# ─── Database ─────────────────────────────────────────────────────────────────
def initialize_event_db():
    conn = sqlite3.connect('event_data.db')
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_name    TEXT,
            event_date    TEXT,
            event_time    TEXT,
            stadium_name  TEXT,
            stadium_image TEXT,
            event_logo    TEXT,
            PRIMARY KEY (event_name, event_date)
        )
    """)
    conn.commit()
    return conn, cursor


def upsert_event(cursor, conn, event_name, event_date, event_time,
                 stadium_name, stadium_image, event_logo):
    cursor.execute("""
        INSERT INTO events (event_name, event_date, event_time, stadium_name, stadium_image, event_logo)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (event_name, event_date)
        DO UPDATE SET
            event_time    = excluded.event_time,
            stadium_name  = excluded.stadium_name,
            stadium_image = excluded.stadium_image,
            event_logo    = excluded.event_logo
    """, (event_name, event_date, event_time, stadium_name, stadium_image, event_logo))
    conn.commit()


# ─── Helpers ──────────────────────────────────────────────────────────────────
def normalise_name(raw: str) -> str:
    """Normalise special characters in team names."""
    for old, new in [('&', 'and'), ('é', 'e'), ('ü', 'u'), ('ó', 'o'), ('á', 'a'),
                     ('ú', 'u'), ('í', 'i'), ('ñ', 'n'), ('ç', 'c')]:
        raw = raw.replace(old, new)
    return raw


def get_product_detail(token: str, product_id: str) -> dict:
    """
    Fetch full product detail from TC API.
    Returns a dict with keys: event_time, stadium_name, stadium_image, event_logo
    Images come directly from data.images.main / data.images.thumb.
    """
    url = f'{TC_API_URL}/product/{product_id}'
    headers = {'accept': 'application/json', 'authorization': f'Bearer {token}'}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json().get('data', {})

        # ── Images ──────────────────────────────────────────────────────────
        images = data.get('images', {})
        # Use 'main' as the event card image (stadium_image / event_logo)
        main_image = images.get('main', '') or images.get('thumb', '')

        # ── Match time ──────────────────────────────────────────────────────
        match = data.get('match', {})
        start = match.get('start', {})
        # Prefer local time, fall back to UTC
        local_dt = start.get('local') or start.get('utc', '')
        event_time = '00:00:00'
        if local_dt:
            # Format: 2026-05-07T20:00:00+01:00 → extract HH:MM:SS
            t_match = re.search(r'T(\d{2}:\d{2}:\d{2})', local_dt)
            if t_match:
                event_time = t_match.group(1)

        # ── Stadium name ─────────────────────────────────────────────────────
        # TC API doesn't expose venue name directly in product detail — leave as TBD
        # event_listing.py will fill in the correct name from TEAM_STADIUM mapping
        stadium_name = 'TBD'

        return {
            'event_time':    event_time,
            'stadium_name':  stadium_name,
            'stadium_image': main_image,
            'event_logo':    main_image,  # Use same image for both fields
        }

    except Exception as e:
        print(f'    Warning: could not fetch product detail for {product_id}: {e}')
        return {
            'event_time':    '00:00:00',
            'stadium_name':  'TBD',
            'stadium_image': '',
            'event_logo':    '',
        }


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print('=== Event Scraper Starting ===')

    token = get_token()
    upcoming = get_upcoming_products(token)
    print(f'{len(upcoming)} upcoming products found.')

    conn, cursor = initialize_event_db()
    saved = 0

    for product in upcoming:
        parts = product['name'].split(' v ')
        if len(parts) < 2:
            continue
        tc_home = parts[0].strip()
        away = parts[1].strip()

        # Only process home teams we care about
        matched_home = next(
            (ht for ht in HOME_TEAMS if ht in tc_home), None
        )
        if not matched_home:
            continue
        if 'Women' in away:
            continue

        event_name = normalise_name(f'{matched_home} v {away}')

        # Parse date from TC API (format: 2026-05-07T20:00:00+00:00 → 2026-05-07)
        raw_date = product.get('date', '')
        event_date = raw_date[:10] if raw_date else ''

        # Fetch product detail for images and time
        meta = get_product_detail(token, product['id'])

        upsert_event(
            cursor, conn,
            event_name=event_name,
            event_date=event_date,
            event_time=meta['event_time'],
            stadium_name=meta['stadium_name'],
            stadium_image=meta['stadium_image'],
            event_logo=meta['event_logo'],
        )
        saved += 1
        print(f'  Saved: {event_name} ({event_date}) — image: {meta["event_logo"][:60] if meta["event_logo"] else "NONE"}')
        time.sleep(0.5)

    conn.close()
    print(f'\n=== Done. {saved} events saved to event_data.db ===')
