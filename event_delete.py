"""
event_delete.py — Tickethouse.net Bot
========================================
Deletes ALL events (and their associated ticket listings) via the
superadmin API endpoint. Uses Token-based authentication with the
superadmin account UUID.

The delete cascades automatically:
    Event → EventSection → Ticket → TicketReservation (all deleted)

Usage (manual):
    python3 event_delete.py              # Delete all events (with confirmation)
    python3 event_delete.py --dry-run    # Preview what would be deleted
    python3 event_delete.py --expired    # Delete only expired (past) events
    python3 event_delete.py --force      # Skip confirmation prompt

Auto-cleanup (called from scraper.py loop):
    from event_delete import auto_cleanup_expired_events
    auto_cleanup_expired_events()        # Silently deletes all expired events

WARNING: Deleting an event also permanently deletes ALL its ticket listings.
"""

import requests
import time
import sys
import traceback

try:
    from config import BASE_URL, SUPERADMIN_USER_ID
except ImportError:
    BASE_URL           = 'https://tickethouse.net'
    SUPERADMIN_USER_ID = '23cfa33d-c781-405a-8805-f0d8523617e1'

DRY_RUN = '--dry-run' in sys.argv
EXPIRED = '--expired' in sys.argv
FORCE   = '--force'   in sys.argv

HEADERS = {
    'Authorization': f'Token {SUPERADMIN_USER_ID}',
    'Content-Type':  'application/json',
}


# ─── Fetch all events ─────────────────────────────────────────────────────────

def get_all_events(expired_only: bool = False) -> list:
    """
    Fetch all events from the API.
    Returns a list of dicts: {event_id, name, date, is_expired}
    """
    all_events = []
    page = 1

    while True:
        # Use sort=all to get ALL events including past/expired ones
        # Default sort='upcoming' only returns future events
        url = f'{BASE_URL}/api/events/all/?page={page}&sort=all&per_page=100'
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f'  Warning: Could not fetch page {page}: {e}')
            break

        data = r.json()

        # The API returns {'events': [...], 'page': N, 'total_pages': N}
        events = data.get('events', data.get('results', []))
        total_pages = data.get('total_pages', 1)

        for event in events:
            event_id   = str(event.get('event_id', ''))
            name       = event.get('name', f'Event-{event_id}')
            date       = event.get('date', '')
            is_expired = event.get('is_expired', False)

            if expired_only and not is_expired:
                continue

            all_events.append({
                'event_id':   event_id,
                'name':       name,
                'date':       date,
                'is_expired': is_expired,
            })

        if page >= total_pages:
            break
        page += 1

    return all_events


# ─── Delete ───────────────────────────────────────────────────────────────────

def delete_event(event: dict) -> tuple:
    """
    Delete an event via the API.
    Returns (success: bool, message: str)
    """
    event_id = event['event_id']
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
        else:
            return False, data.get('error', data.get('message', 'Unknown error'))

    elif r.status_code == 404:
        return True, 'Already deleted (404)'

    elif r.status_code == 403:
        return False, f'403 Forbidden — check superadmin UUID in config.py'

    else:
        try:
            msg = r.json().get('error', r.text[:100])
        except Exception:
            msg = r.text[:100]
        return False, f'HTTP {r.status_code}: {msg}'


# ─── Auto-cleanup (called from the main scraper loop) ────────────────────────

def auto_cleanup_expired_events() -> int:
    """
    Silently fetch all expired events and delete them.
    Designed to be called from the scraper.py main loop each cycle.

    Returns the number of events deleted.
    """
    try:
        expired_events = get_all_events(expired_only=True)
    except Exception as e:
        print(f'  [auto-cleanup] Could not fetch expired events: {e}')
        return 0

    if not expired_events:
        return 0

    print(f'  [auto-cleanup] Found {len(expired_events)} expired event(s) — deleting...')
    deleted = 0
    for event in expired_events:
        name = (event.get('name') or '(unknown)')[:60]
        date = event.get('date', '')
        success, msg = delete_event(event)
        if success:
            deleted += 1
            print(f'    ✓ Deleted: {name} ({date})')
        else:
            print(f'    ✗ Failed:  {name} ({date}) — {msg}')
        time.sleep(0.3)

    print(f'  [auto-cleanup] Done — {deleted}/{len(expired_events)} expired event(s) deleted.')
    return deleted


# ─── Main (manual use) ────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('=' * 60)
    print('  Tickethouse.net — Event Delete Bot')
    print('=' * 60)

    if DRY_RUN:
        print('*** DRY RUN MODE — no events will actually be deleted ***\n')
    if EXPIRED:
        print('*** EXPIRED ONLY MODE — only past events will be deleted ***\n')

    # ── Fetch events ──
    print('\nFetching events from API...')
    try:
        events = get_all_events(expired_only=EXPIRED)
    except Exception as e:
        print(f'\nERROR: Could not fetch events — {e}')
        traceback.print_exc()
        sys.exit(1)

    total = len(events)

    if total == 0:
        print('\nNo events found. Nothing to delete.')
        sys.exit(0)

    # ── Summary table ──
    print(f'\n{"#":<5} {"Event Name":<50} {"Date":<12} {"Expired":<8}')
    print('-' * 80)
    for i, e in enumerate(events, 1):
        name    = (e['name'] or '(unknown)')[:49]
        date    = (e['date'] or '')[:11]
        expired = 'Yes' if e['is_expired'] else 'No'
        print(f'  {i:<4} {name:<50} {date:<12} {expired}')

    print(f'\nTotal: {total} event(s) found.')

    if DRY_RUN:
        print('\nDry run complete. No events were deleted.')
        sys.exit(0)

    # ── Confirmation ──
    if not FORCE:
        print(f'\n⚠  WARNING: This will permanently delete {total} event(s)')
        print('   and ALL their ticket listings!')
        confirm = input('\nType "yes" to confirm deletion: ').strip().lower()
        if confirm != 'yes':
            print('Aborted.')
            sys.exit(0)

    # ── Delete loop ──
    print(f'\nDeleting {total} event(s)...\n')
    deleted = 0
    failed  = 0

    for i, e in enumerate(events, 1):
        name  = e['name'] or '(unknown)'
        label = name[:55]

        print(f'  [{i}/{total}] {label}')
        success, msg = delete_event(e)

        if success:
            deleted += 1
            print(f'    ✓ {msg}')
        else:
            failed += 1
            print(f'    ✗ {msg}')

        # Small delay to be polite to the server
        time.sleep(0.3)

    # ── Summary ──
    print('\n' + '=' * 60)
    print(f'  Done! Deleted: {deleted} | Failed: {failed} | Total: {total}')
    print('=' * 60)

    if failed > 0:
        print(f'\n{failed} event(s) failed to delete.')
        sys.exit(1)
