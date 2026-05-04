"""
expired.py — Tickethouse.net Bot
==================================
Automatically deletes ONLY expired (past) events from tickethouse.net.
An event is expired when its date AND kick-off time have both passed.

This file NEVER touches future or upcoming events — it is safe to run
continuously inside the scraper loop.

Usage (standalone):
    python3 expired.py           # Delete all expired events (no confirmation needed)
    python3 expired.py --dry-run # Preview which events would be deleted

Auto-cleanup (called from scraper.py loop):
    from expired import cleanup_expired_events
    cleanup_expired_events()
"""

import requests
import time
import sys

try:
    from config import BASE_URL, SUPERADMIN_USER_ID
except ImportError:
    BASE_URL           = 'https://tickethouse.net'
    SUPERADMIN_USER_ID = '23cfa33d-c781-405a-8805-f0d8523617e1'

DRY_RUN = '--dry-run' in sys.argv

HEADERS = {
    'Authorization': f'Token {SUPERADMIN_USER_ID}',
    'Content-Type':  'application/json',
}


# ─── Fetch only expired events ────────────────────────────────────────────────

def get_expired_events() -> list:
    """
    Fetch ONLY expired events from the API.
    Returns a list of dicts: {event_id, name, date}
    """
    expired = []
    page = 1

    while True:
        url = f'{BASE_URL}/api/events/all/?page={page}&sort=all&per_page=100'
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f'  [expired] Warning: Could not fetch page {page}: {e}')
            break

        data = r.json()
        events = data.get('events', [])
        total_pages = data.get('total_pages', 1)

        for event in events:
            # Only include events explicitly marked as expired by the server
            if event.get('is_expired', False):
                expired.append({
                    'event_id': str(event.get('event_id', '')),
                    'name':     event.get('name', '(unknown)'),
                    'date':     event.get('date', ''),
                })

        if page >= total_pages:
            break
        page += 1

    return expired


# ─── Delete a single event ────────────────────────────────────────────────────

def delete_event(event_id: str) -> tuple:
    """
    Delete an event by ID via the API.
    Returns (success: bool, message: str)
    """
    url = f'{BASE_URL}/api/events/delete/{event_id}/'
    try:
        r = requests.post(url, headers=HEADERS, timeout=30)
    except requests.exceptions.Timeout:
        return False, 'Timeout'
    except requests.RequestException as e:
        return False, str(e)

    if r.status_code == 200:
        data = r.json()
        if data.get('success'):
            return True, data.get('message', 'Deleted')
        return False, data.get('error', 'Unknown error')
    elif r.status_code == 404:
        return True, 'Already deleted (404)'
    else:
        try:
            msg = r.json().get('error', r.text[:100])
        except Exception:
            msg = r.text[:100]
        return False, f'HTTP {r.status_code}: {msg}'


# ─── Main cleanup function (used by scraper.py loop) ─────────────────────────

def cleanup_expired_events() -> int:
    """
    Fetch all expired events and delete them silently.
    Safe to call every loop cycle — only touches events where
    is_expired=true (date AND kick-off time have already passed).

    Returns the number of events deleted.
    """
    try:
        events = get_expired_events()
    except Exception as e:
        print(f'  [expired] Could not fetch expired events: {e}')
        return 0

    if not events:
        return 0

    print(f'  [expired] {len(events)} expired event(s) found — deleting...')
    deleted = 0

    for event in events:
        name = (event['name'])[:60]
        date = event['date']
        success, msg = delete_event(event['event_id'])
        if success:
            deleted += 1
            print(f'    ✓ Deleted: {name} ({date})')
        else:
            print(f'    ✗ Failed:  {name} ({date}) — {msg}')
        time.sleep(0.3)

    print(f'  [expired] Done — {deleted}/{len(events)} deleted.')
    return deleted


# ─── Standalone usage ─────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('=' * 60)
    print('  Tickethouse.net — Expired Event Cleanup')
    print('=' * 60)

    if DRY_RUN:
        print('*** DRY RUN MODE — no events will be deleted ***\n')

    print('\nFetching expired events...')
    events = get_expired_events()

    if not events:
        print('\nNo expired events found. Nothing to do.')
        sys.exit(0)

    print(f'\n{"#":<5} {"Event Name":<50} {"Date":<12}')
    print('-' * 70)
    for i, e in enumerate(events, 1):
        name = (e['name'] or '(unknown)')[:49]
        date = (e['date'] or '')[:11]
        print(f'  {i:<4} {name:<50} {date}')

    print(f'\nTotal: {len(events)} expired event(s).')

    if DRY_RUN:
        print('\nDry run complete. No events were deleted.')
        sys.exit(0)

    print(f'\nDeleting {len(events)} expired event(s)...\n')
    deleted = 0
    failed  = 0

    for i, e in enumerate(events, 1):
        label = (e['name'] or '(unknown)')[:55]
        print(f'  [{i}/{len(events)}] {label}')
        success, msg = delete_event(e['event_id'])
        if success:
            deleted += 1
            print(f'    ✓ {msg}')
        else:
            failed += 1
            print(f'    ✗ {msg}')
        time.sleep(0.3)

    print('\n' + '=' * 60)
    print(f'  Done! Deleted: {deleted} | Failed: {failed} | Total: {len(events)}')
    print('=' * 60)
