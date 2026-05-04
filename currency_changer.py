"""
Currency conversion utility: EUR → GBP
Uses live exchange rate from an open API, with a fallback rate.
"""
import requests
import time

_cached_rate = None
_cache_time = 0
_CACHE_TTL = 3600  # 1 hour


def get_eur_to_gbp_rate():
    global _cached_rate, _cache_time
    if _cached_rate and (time.time() - _cache_time) < _CACHE_TTL:
        return _cached_rate
    try:
        resp = requests.get(
            'https://api.exchangerate-api.com/v4/latest/EUR',
            timeout=10
        )
        resp.raise_for_status()
        rate = resp.json()['rates']['GBP']
        _cached_rate = rate
        _cache_time = time.time()
        return rate
    except Exception:
        # Fallback rate
        return 0.86


def convert_euro_to_pound(amount):
    """Convert a EUR amount to GBP, rounded to 2 decimal places."""
    rate = get_eur_to_gbp_rate()
    return round(float(amount) * rate, 2)
