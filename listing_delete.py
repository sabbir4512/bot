"""
listing_delete.py — Tickethouse.net Bot
=========================================
Deletes ALL active ticket listings belonging to the bot seller account
(fabionew4512@gmail.com).

Usage:
    python3 listing_delete.py              # Delete all active listings
    python3 listing_delete.py --dry-run    # Preview what would be deleted

The seller can only delete their own unsold listings. Sold tickets are
protected and will be skipped automatically.
"""

import requests
import time
import sys
import traceback

from config import BASE_URL, USER_ID

HEADERS = {'Authorization': f'Token {USER_ID}'}
DRY_RUN = '--dry-run' in sys.argv


def get_all_my_listings() -> list:
    """Fetch all active (unsold) listings for the bot seller."""
    listings = []
    page = 1
    while True:
        resp = requests.get(
            f'{BASE_URL}/api/tickets/my-listings/',
            headers=HEADERS,
            params={'status': 'active', 'page': page, 'per_page': 100},
            timeout=20
        )
        if resp.status_code != 200:
            print(f'  Error fetching listings (page {page}): {resp.status_code} — {resp.text[:100]}')
            break
        data = resp.json()
        batch = data.get('tickets', [])
        listings.extend(batch)
        total_pages = data.get('total_pages', 1)
        print(f'  Fetched page {page}/{total_pages} — {len(batch)} listings')
        if page >= total_pages:
            break
        page += 1
    return listings


def delete_listing(ticket_id: str) -> bool:
    """Delete a single listing by ticket_id. Returns True on success."""
    resp = requests.post(
        f'{BASE_URL}/api/tickets/delete/{ticket_id}/',
        headers=HEADERS,
        timeout=20
    )
    if resp.status_code == 200:
        return True
    else:
        print(f'  Delete failed ({resp.status_code}): {resp.text[:120]}')
        return False


if __name__ == '__main__':
    print('=== Listing Delete Bot Starting ===')
    if DRY_RUN:
        print('*** DRY RUN MODE — no listings will actually be deleted ***\n')

    print('Fetching all active listings...')
    listings = get_all_my_listings()
    total = len(listings)
    print(f'\nFound {total} active listing(s) to delete.\n')

    if total == 0:
        print('Nothing to delete. Exiting.')
        sys.exit(0)

    # Print summary before deleting
    print(f"{'Ticket ID':<40} {'Event':<35} {'Section':<25} {'Qty':>4} {'Price':>8}")
    print('-' * 115)
    for t in listings:
        event_name = t['event']['name'][:34]
        section = t.get('section', '')[:24]
        qty = t['number_of_tickets']
        price = float(t['sell_price'])
        print(f"  {t['ticket_id']:<38} {event_name:<35} {section:<25} {qty:>4} {price:>8.2f}")

    if DRY_RUN:
        print(f'\nDry run complete. {total} listing(s) would be deleted.')
        sys.exit(0)

    print(f'\nDeleting {total} listing(s)...\n')
    deleted = 0
    failed = 0

    for i, t in enumerate(listings, 1):
        ticket_id = t['ticket_id']
        event_name = t['event']['name']
        section = t.get('section', '')
        qty = t['number_of_tickets']

        print(f'  [{i}/{total}] Deleting: {event_name} | {section} | qty={qty} | id={ticket_id}')

        try:
            success = delete_listing(ticket_id)
            if success:
                deleted += 1
                print(f'    ✓ Deleted')
            else:
                failed += 1
        except Exception:
            traceback.print_exc()
            failed += 1

        time.sleep(0.5)  # Be polite to the server

    print(f'\n=== Done. Deleted: {deleted}, Failed: {failed} ===')
