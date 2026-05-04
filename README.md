# Tickethouse.net Bot Suite

Automated listing, pricing, and checking bots for [tickethouse.net](https://tickethouse.net).

---

## First-Time Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set the bot user UUID

The API uses `Authorization: Token <user_uuid>` where the UUID is the database ID of
`mesabbir4512@gmail.com`. Run the one-time setup helper:

```bash
python3 setup_uuid.py
```

This will scan the superadmin accounts page, find the UUID for `mesabbir4512@gmail.com`,
and automatically update `config.py`.

Alternatively, set `USER_ID` manually in `config.py`.

### 3. (Optional) Set the BOT_API_KEY

If you know the `BOT_API_KEY` environment variable value from the server, set it in `config.py`:

```python
BOT_API_KEY = 'your-secret-key'
```

---

## Running the Bots

### Scraper (run continuously)

Fetches ticket data from Travel Connection API every 5 minutes.

```bash
python3 scraper.py
```

### Event Scraper (run once / on schedule)

Scrapes event metadata (time, stadium, images) from travelconnectionleisure.com.

```bash
python3 event_scraper.py
```

### Event Listing (run once / on schedule)

Creates new events on tickethouse.net from `event_data.db`.

```bash
python3 event_listing.py
```

### Listing Bot (run once / on schedule)

Creates new ticket listings on tickethouse.net from `ticket_data.db`.

```bash
python3 listing.py
```

### Pricing Bot (run continuously)

Updates sell prices dynamically based on competition and time-to-event.

```bash
python3 pricing.py
```

### Checking Bot (run continuously)

Verifies all expected listings exist; re-lists any missing quantities.

```bash
python3 checking.py
```

---

## Recommended Run Order

1. `scraper.py` — keep running in background
2. `event_scraper.py` — run once to populate event metadata
3. `event_listing.py` — run once to create events on the website
4. `listing.py` — run once to create initial listings
5. `pricing.py` — keep running in background
6. `checking.py` — keep running in background

---

## File Structure

| File                | Purpose                                              |
|---------------------|------------------------------------------------------|
| `config.py`         | All configuration (URL, USER_ID, teams, pricing)     |
| `currency_changer.py` | EUR → GBP conversion                              |
| `scraper.py`        | Fetches TC API tickets → `ticket_data.db`            |
| `event_scraper.py`  | Scrapes event metadata → `event_data.db`             |
| `event_listing.py`  | Creates events on tickethouse.net                    |
| `listing.py`        | Creates ticket listings on tickethouse.net           |
| `pricing.py`        | Updates listing prices dynamically                   |
| `checking.py`       | Re-lists any missing quantity combinations           |
| `setup_uuid.py`     | One-time helper to find and set USER_ID in config.py |
| `requirements.txt`  | Python dependencies                                  |

---

## API Reference (tickethouse.net)

| Endpoint                                  | Method | Description                    |
|-------------------------------------------|--------|--------------------------------|
| `/api/events/all/`                        | GET    | List all events                |
| `/api/events/create/`                     | POST   | Create a new event             |
| `/api/events/delete/<event_id>/`          | POST   | Delete an event                |
| `/api/events/<event_id>/sections/`        | GET    | List sections for an event     |
| `/api/events/<event_id>/tickets/`         | GET    | List tickets for an event      |
| `/api/events/<event_id>/create-listing/`  | POST   | Create a new ticket listing    |
| `/api/tickets/my-listings/`               | GET    | Get all my active listings     |
| `/api/tickets/update/<ticket_id>/`        | POST   | Update a ticket listing        |
| `/api/tickets/delete/<ticket_id>/`        | POST   | Delete a ticket listing        |
| `/api/bot/receive-tickets/`               | POST   | Bot endpoint (X-Bot-API-Key)   |

**Authentication:** `Authorization: Token <user_uuid>`
