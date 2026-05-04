"""
Configuration for the Tickethouse.net Bot Suite
================================================
Update USER_ID with the UUID of mesabbir4512@gmail.com
"""

# ─── Website ────────────────────────────────────────────────────────────────
BASE_URL = 'https://tickethouse.net'

# UUID of the bot seller account (fabionew4512@gmail.com)
# This is used as the API Token: Authorization: Token <USER_ID>
USER_ID = 'f98fdf9f-3c5c-4854-86e7-fe495fcccee1'  # fabionew4512@gmail.com (Reseller)

# ─── Travel Connection API ──────────────────────────────────────────────────
TC_API_URL = 'https://api.travelconnectionleisure.com/v1'
TC_USERNAME = 'contact@go2events.live'
TC_PASSWORD = 'Romeo2025'
TC_TOKEN_FILE = 'tc_token.json'

# ─── Bot API Key (for receive-tickets endpoint) ─────────────────────────────
# Set this to the BOT_API_KEY environment variable value on the server
# If you don't know it, the scraper will use the standard listing API instead
BOT_API_KEY = None  # e.g. 'your-secret-bot-key'

# ─── Home teams to track ────────────────────────────────────────────────────
HOME_TEAMS = [
    'Arsenal', 'Chelsea', 'Crystal Palace', 'Fulham', 'Liverpool',
    'Manchester City', 'Manchester United', 'Tottenham Hotspur',
    'Aston Villa', 'Brentford', 'Nottingham Forest', 'Leeds United',
    'Rangers FC', 'Atletico Madrid', 'FC Barcelona', 'Real Madrid', 'Sevilla FC'
]

# Teams to skip when listing (not actively listed)
SKIP_TEAMS = {'Real Madrid', 'FC Barcelona', 'Nottingham Forest', 'Rangers FC', 'Sevilla FC'}

# ─── Ticket name → Section name mapping ────────────────────────────────────
DECODING_DICT = {
    'Arsenal': {
        'Cannon Club Level Package': 'VIP Club Level',
        'Cannon Club Level Block 66 Package': 'VIP Club Level',
        'Front Rows Cannon': 'VIP Club Level',
        'Front Rows Cannon Block 66': 'VIP Club Level',
        'Cannon Club Level -  Woolwich Restaurant Package': 'VIP Club Level',
        'Cannon Club Level Block 66 - Woolwich Restaurant Package': 'VIP Club Level',
        'Club Level  Halfway Line': 'VIP Club Level',
        'Club Level Midfield': 'VIP Club Level',
        'Avenell Package': 'VIP Club Level',
        'Diamond Club': 'VIP Club Level',
    },
    'Chelsea': {
        'West View': 'VIP Packages',
        'West View Central': 'VIP Packages',
        'MUSEUM MATCHDAY HOSPTALITY': 'VIP Packages',
        'Rose & Ball Matchday Hospitality - WEST LOWER seats': 'VIP Packages',
        'Rose & Ball Matchday Hospitality \u2013 EAST UPPER seats': 'VIP Packages',
        'Rose & Ball Matchday Hospitality - FRONT ROWS WEST LOWER seats': 'VIP Packages',
        'Rose & Ball Matchday Hospitality - HALFWAY LINE seats': 'VIP Packages',
        'Rose & Ball Matchday Hospitality  - FRONT ROWS WEST LOWER seats': 'VIP Packages',
        'West View with PITCH SIDE PRE MATCH VISIT': 'VIP Packages',
        'MUSEUM MATCHDAY HOSPITALITY with PITCH SIDE PRE MATCH VISIT': 'VIP Packages',
        'Blues Dining Match Day Hospitality': 'Longside Lower Tier',
    },
    'Crystal Palace': {
        'White Horse Lane Hospitality Box': 'VIP Packages',
        'General Admission Ticket': 'Longside Tier',
    },
    'Fulham': {
        'Putney End Stand (P3/P4)': 'Shortside Tier',
        'New Riverside Stand Silver': 'Longside Upper Tier',
        'New Riverside Stand Gold': 'Longside Upper Tier',
        'Matchday Plus': 'VIP Packages',
        'The Dugout': 'VIP Packages',
    },
    'Liverpool': {
        'Brodies': 'VIP Packages',
        'Premium Brodies': 'VIP Packages',
        'Front Rows Brodies': 'VIP Packages',
        'Central Front Rows Brodies': 'VIP Packages',
        'Premier Club Hospitality Ticket': 'VIP Packages',
        'Kop End Premier Club Hospitality': 'VIP Packages',
    },
    'Manchester City': {
        '93:20 Lounge ticket': 'VIP Packages',
        'Kits Sports Bar': 'VIP Packages',
        'The Citizens Hospitality': 'VIP Packages',
    },
    'Manchester United': {
        'TicketPlus': 'VIP Packages',
        'North East Executive Quadrant 500 Club with food included': 'VIP Packages',
        'North East Executive Quadrant The Academy with food included': 'VIP Packages',
        'North West Executive Quadrant 100 Club with food included': 'VIP Packages',
        'North West Executive Quadrant Kit Room with food included': 'VIP Packages',
        'Pre Match Museum Package Block N3408': 'VIP Packages',
        'Pre Match Museum Package Block N3407-N3402': 'VIP Packages',
        'Victoria Warehouse Hospitality': 'VIP Packages',
    },
    'Tottenham Hotspur': {
        'General Admission - Short Side Upper Tier': 'Shortside Upper Tier',
        'General Admission - Long side Upper Tier': 'Longside Upper Tier',
        'East Premium Seat Package, corner location': 'VIP Packages',
        'East Premium Seat Package, long side': 'VIP Packages',
        'East Premium Seat Package, halfway line': 'VIP Packages',
        'East Premium Seat Package, halfway line ( guaranteed row 1 & 2 )': 'VIP Packages',
        'The Locker Room': 'VIP Packages',
    },
    'Aston Villa': {
        'Doug Ellis Stand': 'Longside Upper',
        'Trinity Road Stand': 'Longside Upper',
        'Holte End Stand': 'Shortside Upper',
        'Lower Grounds Premium with Trinity Stand Seats': 'VIP Packages',
    },
    'Brentford': {
        'Official Brentford FC South Stand ticket': 'Longside Upper',
        'Official Brentford FC ticket + Hospitality': 'VIP Packages',
    },
    'Leeds United': {
        "Yeboah\u2019s Crossbar Package": 'VIP Packages',
        'Centenary Pavilion Hospitality Package': 'VIP Packages',
    },
    'Rangers FC': {
        'Club Deck Plus': 'VIP Packages',
        'Museum': 'VIP Packages',
        'Gordon Ramsay VIP Ibrox package': 'VIP Packages',
    },
    'Atletico Madrid': {
        'VIP Club East/East Club': 'VIP Hospitality',
    },
    'Sevilla FC': {
        'VIP Premium Glasgow': 'VIP Hospitality',
        'Longside': 'Lateral Tribuna Alto N43',
        'Shortside': 'Gol Tribuna Alto N46',
    },
}

# ─── Pricing multipliers by days-to-event ──────────────────────────────────
PROFIT_RANGES = [
    (14,  1.15),   # within 14 days
    (30,  1.20),   # within 30 days
    (60,  1.25),   # within 60 days
    (90,  1.30),   # within 90 days
    (120, 1.35),   # within 120 days
    (999, 1.40),   # more than 120 days
]

# ─── Listing defaults ───────────────────────────────────────────────────────
LISTING_ROW = 'XMZX'
LISTING_TICKET_TYPE = 'mobile-transfer'
LISTING_UPLOAD_CHOICE = 'later'
LISTING_STARTING_SEAT = 100
CHECKING_STARTING_SEAT = 200
