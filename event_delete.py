"""
event_delete.py — Tickethouse.net Bot
========================================
Deletes ALL events (and their associated ticket listings) via the superadmin
web interface. Uses Django session-based authentication — no API token needed.

Credentials used: testforpermisgoo@gmail.com (superadmin account)

Usage:
    python3 event_delete.py              # Delete all events (with confirmation)
    python3 event_delete.py --dry-run    # Preview what would be deleted
    python3 event_delete.py --expired    # Delete only expired (past) events

WARNING: Deleting an event also deletes ALL its ticket listings permanently.
"""

import requests
import time
import sys
import re
import traceback
from bs4 import BeautifulSoup

from config import BASE_URL, SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD

DRY_RUN   = '--dry-run'  in sys.argv
EXPIRED   = '--expired'  in sys.argv


# ─── Session auth ─────────────────────────────────────────────────────────────

def get_superadmin_session() -> requests.Session:
    """Log in to the Django admin and return an authenticated session."""
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})

    # Get CSRF token from admin login page
    r = session.get(f'{BASE_URL}/admin/login/?next=/admin/', timeout=20)
    soup = BeautifulSoup(r.text, 'html.parser')
    csrf_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
    if not csrf_input:
        raise RuntimeError('Could not find CSRF token on admin login page')
    csrf = csrf_input['value']

    # Login
    resp = session.post(
        f'{BASE_URL}/admin/login/?next=/admin/',
        data={
            'csrfmiddlewaretoken': csrf,
            'username': SUPERADMIN_EMAIL,
            'password': SUPERADMIN_PASSWORD,
            'next': '/admin/',
        },
        headers={'Referer': f'{BASE_URL}/admin/login/?next=/admin/'},
        timeout=20,
        allow_redirects=True,
    )
    if '/admin/' not in resp.url and 'login' in resp.url:
        raise RuntimeError(f'Admin login failed — redirected to: {resp.url}')
    print(f'  Superadmin session established (logged in as {SUPERADMIN_EMAIL})')
    return session


# ─── Event discovery ──────────────────────────────────────────────────────────

def get_all_event_delete_urls(session: requests.Session, expired_only: bool = False) -> list:
    """
    Scrape the superadmin events list (and expired events list) to collect
    all event delete URLs.  Returns a list of dicts:
        {'name': str, 'date': str, 'delete_url': str}
    """
    results = []
    endpoints = []

    if expired_only:
        endpoints = [f'{BASE_URL}/superadmin/expired-events/']
    else:
        endpoints = [
            f'{BASE_URL}/superadmin/events/',
            f'{BASE_URL}/superadmin/expired-events/',
        ]

    for base_endpoint in endpoints:
        page = 1
        while True:
            url = f'{base_endpoint}?page={page}&per_page=100'
            r = session.get(url, timeout=20)
            if r.status_code != 200:
                print(f'  Warning: {url} returned {r.status_code}')
                break
            soup = BeautifulSoup(r.text, 'html.parser')

            # Collect delete form actions
            delete_forms = soup.find_all('form', action=re.compile(r'/superadmin/events/.+/delete/'))
            if not delete_forms:
                break

            for form in delete_forms:
                action = form.get('action', '')
                # Try to find event name nearby
                card = form.find_parent(class_=re.compile(r'event|card|row', re.I))
                name = ''
                date = ''
                if card:
                    name_tag = card.find(class_=re.compile(r'event.?name|title|name', re.I))
                    date_tag = card.find(class_=re.compile(r'date|time', re.I))
                    if name_tag:
                        name = name_tag.get_text(strip=True)
                    if date_tag:
                        date = date_tag.get_text(strip=True)

                # Deduplicate
                if not any(e['delete_url'] == action for e in results):
                    results.append({'name': name, 'date': date, 'delete_url': action})

            # Check for next page
            next_link = soup.find('a', href=re.compile(rf'page={page + 1}'))
            if not next_link:
                break
            page += 1

        print(f'  Collected {len(results)} events from {base_endpoint}')

    return results


def delete_event(session: requests.Session, delete_url: str) -> bool:
    """
    POST to the superadmin delete URL to delete an event.
    Returns True on success.
    """
    full_url = f'{BASE_URL}{delete_url}' if delete_url.startswith('/') else delete_url

    # Need a fresh CSRF token from the events list page
    r_csrf = session.get(f'{BASE_URL}/superadmin/events/', timeout=20)
    soup = BeautifulSoup(r_csrf.text, 'html.parser')
    csrf_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
    csrf = csrf_input['value'] if csrf_input else ''

    resp = session.post(
        full_url,
        data={'csrfmiddlewaretoken': csrf},
        headers={'Referer': f'{BASE_URL}/superadmin/events/'},
        timeout=20,
        allow_redirects=True,
    )
    # Success = redirected to events list
    if resp.status_code in (200, 302) and 'superadmin/events' in resp.url:
        return True
    # Also accept 200 with success message in body
    if resp.status_code == 200 and ('deleted successfully' in resp.text.lower() or
                                     'superadmin/events' in resp.url):
        return True
    print(f'  Unexpected response: {resp.status_code} — {resp.url}')
    return False


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('=== Event Delete Bot Starting ===')
    if DRY_RUN:
        print('*** DRY RUN MODE — no events will actually be deleted ***\n')
    if EXPIRED:
        print('*** EXPIRED ONLY MODE — only past events will be deleted ***\n')

    print('Establishing superadmin session...')
    try:
        session = get_superadmin_session()
    except Exception as e:
        print(f'ERROR: Could not log in — {e}')
        sys.exit(1)

    print('Fetching event list...')
    events = get_all_event_delete_urls(session, expired_only=EXPIRED)
    total = len(events)
    print(f'\nFound {total} event(s) to delete.\n')

    if total == 0:
        print('Nothing to delete. Exiting.')
        sys.exit(0)

    # Print summary
    print(f"{'#':<4} {'Name':<45} {'Date':<12}")
    print('-' * 65)
    for i, e in enumerate(events, 1):
        name = (e['name'] or '(unknown)')[:44]
        date = (e['date'] or '')[:11]
        print(f"  {i:<3} {name:<45} {date:<12}")

    if DRY_RUN:
        print(f'\nDry run complete. {total} event(s) would be deleted.')
        sys.exit(0)

    # Safety confirmation
    print(f'\n⚠  WARNING: This will permanently delete {total} event(s) and ALL their ticket listings!')
    confirm = input('Type "yes" to confirm: ').strip().lower()
    if confirm != 'yes':
        print('Aborted.')
        sys.exit(0)

    print(f'\nDeleting {total} event(s)...\n')
    deleted = 0
    failed  = 0

    for i, e in enumerate(events, 1):
        name       = e['name'] or '(unknown)'
        date       = e['date'] or ''
        delete_url = e['delete_url']

        print(f'  [{i}/{total}] Deleting: {name} ({date})')

        try:
            success = delete_event(session, delete_url)
            if success:
                deleted += 1
                print(f'    ✓ Deleted')
            else:
                failed += 1
                print(f'    ✗ Failed')
        except Exception:
            traceback.print_exc()
            failed += 1

        time.sleep(0.8)  # Be polite to the server

    print(f'\n=== Done. Deleted: {deleted}, Failed: {failed} ===')
