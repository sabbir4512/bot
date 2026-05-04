"""
api_helpers.py — Shared API utilities for tickethouse.net bots
================================================================
Provides helper functions used by listing.py, pricing.py, and checking.py.

Key functions:
  - get_section_id(event_id, section_name) — Returns the integer section ID
    for a given event and section name. Uses the event's ticket list first,
    then falls back to the superadmin event update page.
  - get_all_events() — Returns all events from the website.
  - get_my_listings() — Returns all active listings for the bot user.
"""

import requests
from bs4 import BeautifulSoup

from config import BASE_URL, USER_ID

# ─── Superadmin session (used as fallback for section IDs) ───────────────────
_admin_session = None

def _get_admin_session() -> requests.Session:
    global _admin_session
    if _admin_session is not None:
        return _admin_session
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    r = session.get(f'{BASE_URL}/admin/login/?next=/admin/', timeout=20)
    soup = BeautifulSoup(r.text, 'html.parser')
    csrf_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
    if not csrf_input:
        print('Admin login page not found — section ID fallback unavailable.')
        return session
    csrf = csrf_input['value']
    session.post(
        f'{BASE_URL}/admin/login/?next=/admin/',
        data={
            'csrfmiddlewaretoken': csrf,
            'username': 'testforpermisgoo@gmail.com',
            'password': 'Sh97436410@',
            'next': '/admin/'
        },
        headers={'Referer': f'{BASE_URL}/admin/login/?next=/admin/'},
        timeout=20,
        allow_redirects=True
    )
    _admin_session = session
    return session


def _get_event_uuid_from_admin(event_id: str) -> str | None:
    """Get the UUID (primary key) of an event from the superadmin event list."""
    session = _get_admin_session()
    page = 1
    while True:
        r = session.get(
            f'{BASE_URL}/superadmin/events/?page={page}',
            timeout=20
        )
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.text, 'html.parser')
        # Look for event links with UUIDs
        import re
        # Find all event update links
        for a in soup.find_all('a', href=True):
            href = a['href']
            match = re.search(r'/superadmin/events/([0-9a-f-]{36})/update/', href)
            if match:
                uuid = match.group(1)
                # Check if this event's page mentions our event_id
                r2 = session.get(f'{BASE_URL}/superadmin/events/{uuid}/update/', timeout=15)
                if r2.status_code == 200:
                    soup2 = BeautifulSoup(r2.text, 'html.parser')
                    # Look for the event_id in the page
                    if f'event_id={event_id}' in r2.text or event_id in r2.url:
                        return uuid
                    # Check the name field to match
                    name_input = soup2.find('input', {'name': 'name'})
                    if name_input:
                        # We'll match by checking the section IDs later
                        pass

        # Check if there's a next page
        next_link = soup.find('a', string=lambda t: t and 'next' in t.lower())
        if not next_link:
            break
        page += 1
    return None


def get_section_id_from_admin(event_id: str, section_name: str) -> int | None:
    """
    Get section ID from the superadmin event update page.
    This is a fallback for when the sections API returns 500.
    
    Strategy: scan the superadmin event list, find the event by event_id,
    then read the section_id hidden inputs.
    """
    import re
    session = _get_admin_session()

    # First, get all events from the API to find the event name
    headers = {'Authorization': f'Token {USER_ID}'}
    r_events = requests.get(
        f'{BASE_URL}/api/events/all/',
        headers=headers,
        params={'page': 1, 'per_page': 200},
        timeout=20
    )
    if r_events.status_code != 200:
        return None

    target_event_name = None
    for e in r_events.json().get('events', []):
        if e['event_id'] == event_id:
            target_event_name = e['name']
            break

    if not target_event_name:
        return None

    # Scan superadmin events pages to find the matching event
    page = 1
    while True:
        r = session.get(f'{BASE_URL}/superadmin/events/?page={page}', timeout=20)
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.text, 'html.parser')

        for a in soup.find_all('a', href=True):
            href = a['href']
            match = re.search(r'/superadmin/events/([0-9a-f-]{36})/update/', href)
            if not match:
                continue
            uuid = match.group(1)
            r2 = session.get(f'{BASE_URL}/superadmin/events/{uuid}/update/', timeout=15)
            if r2.status_code != 200:
                continue
            soup2 = BeautifulSoup(r2.text, 'html.parser')
            name_input = soup2.find('input', {'name': 'name'})
            if not name_input:
                continue
            event_name_on_page = name_input.get('value', '')
            if event_name_on_page.lower() != target_event_name.lower():
                continue

            # Found the event — now extract section IDs
            section_ids = soup2.find_all('input', {'name': 'section_id'})
            section_names = soup2.find_all('input', {'name': 'section_name'})
            for sid_input, sname_input in zip(section_ids, section_names):
                sid = sid_input.get('value', '')
                sname = sname_input.get('value', '')
                if sname.lower() == section_name.lower() and sid:
                    try:
                        return int(sid)
                    except ValueError:
                        pass
            # Event found but section not found
            print(f"  Section '{section_name}' not found in event '{target_event_name}'.")
            return None

        # Check for next page
        has_next = soup.find('a', href=lambda h: h and f'page={page+1}' in h)
        if not has_next:
            break
        page += 1

    return None


def get_section_id(event_id: str, section_name: str) -> int | None:
    """
    Get the section ID for a given event and section name.

    Tries three methods in order:
    1. Sections API endpoint — fast, always works for any event
    2. Event's ticket list — fallback if sections endpoint fails
    3. Superadmin event update page — last resort
    """
    headers = {'Authorization': f'Token {USER_ID}'}

    # Method 1: Sections API endpoint (primary — works even with 0 tickets)
    try:
        r = requests.get(
            f'{BASE_URL}/api/events/{event_id}/sections/',
            headers=headers,
            timeout=20
        )
        if r.status_code == 200:
            data = r.json()
            for section in data.get('sections', []):
                if section.get('name', '').lower() == section_name.lower():
                    return section['id']
    except Exception as e:
        print(f'  Method 1 (sections API) error: {e}')

    # Method 2: Get section ID from existing tickets
    try:
        r = requests.get(
            f'{BASE_URL}/api/events/{event_id}/tickets/',
            headers=headers,
            timeout=20
        )
        if r.status_code == 200:
            data = r.json()
            for ticket in data.get('tickets', []):
                sec = ticket.get('section', {})
                if sec.get('name', '').lower() == section_name.lower():
                    return sec['id']
    except Exception as e:
        print(f'  Method 2 (tickets) error: {e}')

    # Method 3: Get section ID from superadmin event update page
    print(f"  Section '{section_name}' not in sections/tickets — trying admin page...")
    try:
        section_id = get_section_id_from_admin(event_id, section_name)
        if section_id:
            return section_id
    except Exception as e:
        print(f'  Method 3 (admin) error: {e}')

    print(f"  Could not find section ID for '{section_name}' in event {event_id}.")
    return None


def get_all_events() -> list:
    """Return all events from tickethouse.net."""
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
    return events


def get_my_listings() -> list:
    """Return all active listings for the bot seller."""
    headers = {'Authorization': f'Token {USER_ID}'}
    listings = []
    page = 1
    while True:
        resp = requests.get(
            f'{BASE_URL}/api/tickets/my-listings/',
            headers=headers,
            params={'status': 'active', 'page': page, 'per_page': 100},
            timeout=20
        )
        if resp.status_code != 200:
            print(f'My-listings error: {resp.status_code}')
            break
        data = resp.json()
        listings.extend(data.get('tickets', []))
        if page >= data.get('total_pages', 1):
            break
        page += 1
    return listings
