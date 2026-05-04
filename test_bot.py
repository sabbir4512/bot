"""
test_bot.py — Integration tests for the tickethouse.net bot
=============================================================
Tests all API endpoints used by the bot without creating real data.
"""
import requests
import json
import sys

BASE_URL = 'https://tickethouse.net'
USER_ID = 'f98fdf9f-3c5c-4854-86e7-fe495fcccee1'
headers = {'Authorization': f'Token {USER_ID}'}

PASS = '\033[92m✓\033[0m'
FAIL = '\033[91m✗\033[0m'

def test(name, condition, detail=''):
    if condition:
        print(f'{PASS} {name}')
    else:
        print(f'{FAIL} {name} — {detail}')
    return condition

all_passed = True

print('=== Tickethouse.net Bot API Tests ===\n')

# ─── 1. Auth test ─────────────────────────────────────────────────────────────
print('--- Authentication ---')
r = requests.get(f'{BASE_URL}/api/tickets/my-listings/', headers=headers, timeout=20)
ok = test('Auth token valid (my-listings returns 200)', r.status_code == 200, f'Got {r.status_code}: {r.text[:100]}')
all_passed &= ok

if r.status_code == 200:
    data = r.json()
    tickets = data.get('tickets', [])
    test(f'My-listings response has tickets field', 'tickets' in data)
    print(f'  Active listings: {len(tickets)}')
    if tickets:
        t = tickets[0]
        print(f'  Sample: {t["event"]["name"]} | {t["section"]} | qty={t["number_of_tickets"]} | price={t["sell_price"]}')

# ─── 2. Events API ────────────────────────────────────────────────────────────
print('\n--- Events API ---')
r2 = requests.get(f'{BASE_URL}/api/events/all/', headers=headers, params={'page': 1, 'per_page': 5}, timeout=20)
ok2 = test('Events all returns 200', r2.status_code == 200, f'Got {r2.status_code}')
all_passed &= ok2

if r2.status_code == 200:
    data2 = r2.json()
    events = data2.get('events', [])
    total = data2.get('total_events', 0)
    test(f'Events response has events field', 'events' in data2)
    print(f'  Total events: {total}')
    if events:
        e = events[0]
        print(f'  Sample: {e["name"]} ({e["date"]}) — ID: {e["event_id"]}')
        
        # ─── 3. Event tickets ─────────────────────────────────────────────────
        print('\n--- Event Tickets API ---')
        r3 = requests.get(f'{BASE_URL}/api/events/{e["event_id"]}/tickets/', headers=headers, timeout=20)
        ok3 = test(f'Event tickets for {e["name"]} returns 200', r3.status_code == 200, f'Got {r3.status_code}')
        all_passed &= ok3
        if r3.status_code == 200:
            tdata = r3.json()
            tlist = tdata.get('tickets', [])
            print(f'  Tickets for this event: {len(tlist)}')
            if tlist:
                sec = tlist[0]['section']
                print(f'  Sample section: {sec["name"]} (ID: {sec["id"]})')
        
        # ─── 4. Section ID lookup ─────────────────────────────────────────────
        print('\n--- Section ID Lookup (api_helpers) ---')
        try:
            from api_helpers import get_section_id
            # Find a section name from the tickets
            if r3.status_code == 200 and tlist:
                section_name = tlist[0]['section']['name']
                expected_id = tlist[0]['section']['id']
                found_id = get_section_id(e['event_id'], section_name)
                ok4 = test(
                    f'get_section_id("{section_name}") returns correct ID',
                    found_id == expected_id,
                    f'Expected {expected_id}, got {found_id}'
                )
                all_passed &= ok4
        except Exception as ex:
            test('get_section_id import', False, str(ex))

# ─── 5. Ticket update API ─────────────────────────────────────────────────────
print('\n--- Ticket Update API ---')
if r.status_code == 200 and tickets:
    t = tickets[0]
    tid = t['ticket_id']
    # Just test with the same price (no actual change)
    update_payload = {
        'upload_choice':           t.get('upload_choice', 'later'),
        'upload_by':               t.get('upload_by', ''),
        'number_of_tickets':       t['number_of_tickets'],
        'section':                 t['section_id'],
        'row':                     t.get('row', 'XMZX'),
        'seats':                   ', '.join(str(s) for s in t.get('seats', [])),
        'face_value':              float(t['face_value']),
        'ticket_type':             t.get('ticket_type', 'mobile-transfer'),
        'benefits_and_Restrictions': t.get('benefits_and_Restrictions', []),
        'sell_price':              float(t['sell_price']),
        'sell_together':           False,
    }
    r_upd = requests.post(
        f'{BASE_URL}/api/tickets/update/{tid}/',
        headers={**headers, 'Content-Type': 'application/json'},
        data=json.dumps(update_payload),
        timeout=20
    )
    ok5 = test(f'Ticket update returns 200/201', r_upd.status_code in (200, 201), f'Got {r_upd.status_code}: {r_upd.text[:150]}')
    all_passed &= ok5
else:
    print('  (Skipped — no active listings to test update)')

# ─── 6. Config import ─────────────────────────────────────────────────────────
print('\n--- Config Import ---')
try:
    from config import (
        BASE_URL as CFG_URL, USER_ID as CFG_UID,
        TC_API_URL, TC_USERNAME, TC_PASSWORD,
        HOME_TEAMS, SKIP_TEAMS, DECODING_DICT,
        PROFIT_RANGES, LISTING_ROW, LISTING_TICKET_TYPE,
        LISTING_UPLOAD_CHOICE, LISTING_STARTING_SEAT, CHECKING_STARTING_SEAT
    )
    test('config.py imports OK', True)
    test('BASE_URL is tickethouse.net', 'tickethouse.net' in CFG_URL)
    test('USER_ID is set', bool(CFG_UID) and 'REPLACE' not in CFG_UID)
    test('HOME_TEAMS list is populated', len(HOME_TEAMS) > 0)
    test('DECODING_DICT has entries', len(DECODING_DICT) > 0)
    test('PROFIT_RANGES is set', len(PROFIT_RANGES) > 0)
except Exception as ex:
    test('config.py imports', False, str(ex))

# ─── 7. Currency converter ────────────────────────────────────────────────────
print('\n--- Currency Converter ---')
try:
    from currency_changer import convert_euro_to_pound
    result = convert_euro_to_pound(100)
    test('EUR→GBP conversion works', isinstance(result, float) and result > 0, f'Got {result}')
except Exception as ex:
    test('currency_changer import', False, str(ex))

# ─── Summary ──────────────────────────────────────────────────────────────────
print(f'\n{"="*40}')
if all_passed:
    print('All tests passed! ✓')
else:
    print('Some tests failed. See above for details.')
    sys.exit(1)
