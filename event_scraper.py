"""
event_scraper.py — Tickethouse.net Bot
========================================
Scrapes event metadata (match name, date, time, stadium images, logos)
from travelconnectionleisure.com and stores them in event_data.db.

Run once (or on a schedule): python3 event_scraper.py
"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import time
import traceback
import re

from config import TC_API_URL, TC_USERNAME, TC_PASSWORD, TC_TOKEN_FILE, HOME_TEAMS
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


# ─── Scraping ─────────────────────────────────────────────────────────────────
def normalise_name(raw: str) -> str:
    for old, new in [('&', 'and'), ('é', 'e'), ('ü', 'u'), ('ó', 'o'), ('á', 'a')]:
        raw = raw.replace(old, new)
    return raw


def scrape_event_page(url: str) -> dict:
    """Scrape a single event page on travelconnectionleisure.com for metadata."""
    try:
        resp = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Time
        time_tag = soup.find('span', class_=re.compile(r'time|kick.?off', re.I))
        event_time = time_tag.get_text(strip=True) if time_tag else '00:00:00'
        # Normalise to HH:MM:SS
        t_match = re.search(r'(\d{1,2}):(\d{2})', event_time)
        if t_match:
            event_time = f"{int(t_match.group(1)):02d}:{t_match.group(2)}:00"
        else:
            event_time = '00:00:00'

        # Stadium name
        stadium_tag = soup.find(class_=re.compile(r'venue|stadium|ground', re.I))
        stadium_name = stadium_tag.get_text(strip=True) if stadium_tag else 'TBD'

        # Stadium image
        og_image = soup.find('meta', property='og:image')
        stadium_image = og_image['content'] if og_image else ''

        # Event logo (team badge / event image)
        logo_img = soup.find('img', class_=re.compile(r'logo|badge|crest', re.I))
        event_logo = logo_img['src'] if logo_img else ''

        return {
            'event_time':    event_time,
            'stadium_name':  stadium_name,
            'stadium_image': stadium_image,
            'event_logo':    event_logo,
        }
    except Exception:
        traceback.print_exc()
        return {
            'event_time':    '00:00:00',
            'stadium_name':  'TBD',
            'stadium_image': '',
            'event_logo':    '',
        }


def get_product_detail_url(token: str, product_id: str) -> str:
    """Get the public URL for a product from the TC API."""
    url = f'{TC_API_URL}/product/{product_id}'
    headers = {'accept': 'application/json', 'authorization': f'Bearer {token}'}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.json().get('url', '')
    except Exception:
        return ''


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
        event_date = product['date']

        # Scrape the event page for metadata
        detail_url = get_product_detail_url(token, product['id'])
        if detail_url:
            meta = scrape_event_page(detail_url)
        else:
            meta = {
                'event_time':    '00:00:00',
                'stadium_name':  'TBD',
                'stadium_image': '',
                'event_logo':    '',
            }

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
        print(f'  Saved: {event_name} ({event_date})')
        time.sleep(1)

    conn.close()
    print(f'\n=== Done. {saved} events saved to event_data.db ===')
