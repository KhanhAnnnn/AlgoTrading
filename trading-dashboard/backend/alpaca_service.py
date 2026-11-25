"""
alpaca_service.py — Read-Only Alpaca Paper Trading Service (GĐ15.1)
Strictly connects to https://paper-api.alpaca.markets for portfolio telemetry.
Zero live trading capability; no order placement methods allowed in dashboard.
Supports Last-Known-Good fault tolerance with timestamp provenance and cache age tracking.
"""
import os
import sys
import time
import requests
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Add libs path if needed
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
libs_dir = os.path.join(base_dir, 'libs')
if libs_dir not in sys.path:
    sys.path.insert(0, libs_dir)

try:
    from alpaca_config.keys import config
except ImportError:
    config = {}

PAPER_BASE_URL = config.get('trade_api_base_url', os.environ.get('ALPACA_TRADE_BASE_URL', 'https://paper-api.alpaca.markets'))
KEY_ID = config.get('key_id', os.environ.get('ALPACA_KEY_ID', ''))
SECRET_KEY = config.get('secret_key', os.environ.get('ALPACA_SECRET_KEY', ''))

# Hard assertion to prevent any live trading endpoints
if 'paper-api' not in PAPER_BASE_URL:
    raise RuntimeError(f"CRITICAL SAFETY VIOLATION: '{PAPER_BASE_URL}' is not an Alpaca Paper Trading endpoint.")


def _get_headers() -> Dict[str, str]:
    return {
        'APCA-API-KEY-ID': KEY_ID,
        'APCA-API-SECRET-KEY': SECRET_KEY,
        'Content-Type': 'application/json',
    }


def get_account() -> Dict[str, Any]:
    """Retrieve Paper account equity, cash, and buying power."""
    if not KEY_ID or not SECRET_KEY:
        return {'status': 'UNCONFIGURED', 'equity': 0.0, 'cash': 0.0, 'buying_power': 0.0}
    try:
        resp = requests.get(f"{PAPER_BASE_URL}/v2/account", headers=_get_headers(), timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {
                'id': data.get('id'),
                'status': data.get('status', 'ACTIVE'),
                'currency': data.get('currency', 'USD'),
                'equity': float(data.get('equity', 0.0)),
                'cash': float(data.get('cash', 0.0)),
                'buying_power': float(data.get('buying_power', 0.0)),
                'portfolio_value': float(data.get('portfolio_value', 0.0)),
                'pattern_day_trader': data.get('pattern_day_trader', False),
            }
        return {'status': f"ERROR_{resp.status_code}", 'error': resp.text}
    except Exception as e:
        return {'status': 'ERROR', 'error': str(e)}


def get_positions() -> List[Dict[str, Any]]:
    """Retrieve current open positions."""
    if not KEY_ID or not SECRET_KEY:
        return []
    try:
        resp = requests.get(f"{PAPER_BASE_URL}/v2/positions", headers=_get_headers(), timeout=5)
        if resp.status_code == 200:
            positions = []
            for p in resp.json():
                positions.append({
                    'symbol': p.get('symbol'),
                    'qty': float(p.get('qty', 0.0)),
                    'side': p.get('side'),
                    'current_price': float(p.get('current_price', 0.0)),
                    'avg_entry_price': float(p.get('avg_entry_price', 0.0)),
                    'market_value': float(p.get('market_value', 0.0)),
                    'unrealized_pl': float(p.get('unrealized_pl', 0.0)),
                    'unrealized_plpc': float(p.get('unrealized_plpc', 0.0)),
                })
            return positions
        return []
    except Exception:
        return []


def get_orders(limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieve recent paper trading orders."""
    if not KEY_ID or not SECRET_KEY:
        return []
    try:
        resp = requests.get(f"{PAPER_BASE_URL}/v2/orders?status=all&limit={limit}", headers=_get_headers(), timeout=5)
        if resp.status_code == 200:
            orders = []
            for o in resp.json():
                orders.append({
                    'id': o.get('id'),
                    'client_order_id': o.get('client_order_id'),
                    'symbol': o.get('symbol'),
                    'qty': o.get('qty'),
                    'side': o.get('side'),
                    'type': o.get('type'),
                    'time_in_force': o.get('time_in_force'),
                    'status': o.get('status'),
                    'submitted_at': o.get('submitted_at') or o.get('created_at'),
                    'filled_at': o.get('filled_at'),
                    'filled_qty': o.get('filled_qty', '0'),
                    'filled_avg_price': o.get('filled_avg_price'),
                })
            return orders
        return []
    except Exception:
        return []


_CLOCK_CACHE = None
_CLOCK_CACHE_TIME = 0.0


def get_clock() -> Dict[str, Any]:
    """Retrieve market open/close status from Alpaca with 15s cache."""
    global _CLOCK_CACHE, _CLOCK_CACHE_TIME
    if _CLOCK_CACHE is not None and (time.time() - _CLOCK_CACHE_TIME) < 15.0:
        return _CLOCK_CACHE

    if not KEY_ID or not SECRET_KEY:
        return {'is_open': False, 'error': 'Unconfigured'}
    try:
        resp = requests.get(f"{PAPER_BASE_URL}/v2/clock", headers=_get_headers(), timeout=5)
        if resp.status_code == 200:
            res = resp.json()
            _CLOCK_CACHE = res
            _CLOCK_CACHE_TIME = time.time()
            return res
        return {'is_open': False, 'error': resp.text}
    except Exception as e:
        return {'is_open': False, 'error': str(e)}


_PORTFOLIO_CACHE = None
_PORTFOLIO_CACHE_TIME = 0.0
_LAST_KNOWN_GOOD_PORTFOLIO = None
_LAST_KNOWN_GOOD_TIME = None
_LAST_KNOWN_GOOD_TS = 0.0


def get_portfolio_summary() -> Dict[str, Any]:
    """
    Provides consolidated portfolio summary for Quant Analytics Terminal with 5s micro-cache,
    timestamp provenance, cache age, and Last-Known-Good fault tolerance.
    """
    global _PORTFOLIO_CACHE, _PORTFOLIO_CACHE_TIME
    global _LAST_KNOWN_GOOD_PORTFOLIO, _LAST_KNOWN_GOOD_TIME, _LAST_KNOWN_GOOD_TS

    now = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    if _PORTFOLIO_CACHE is not None and (now - _PORTFOLIO_CACHE_TIME) < 5.0:
        cached_copy = dict(_PORTFOLIO_CACHE)
        cached_copy['cache_age_sec'] = round(now - _PORTFOLIO_CACHE_TIME, 1)
        return cached_copy

    account = get_account()
    api_failed = account.get('status', '').startswith('ERROR') or account.get('status') == 'UNCONFIGURED'

    if not api_failed:
        positions = get_positions()
        orders = get_orders(limit=50)

        total_unrealized_pl = sum(p.get('unrealized_pl', 0.0) for p in positions)
        total_cost_basis = sum(p.get('qty', 0.0) * p.get('avg_entry_price', 0.0) for p in positions)
        unrealized_plpc = (total_unrealized_pl / total_cost_basis * 100.0) if total_cost_basis > 0 else 0.0

        open_orders = [o for o in orders if o.get('status') in ('accepted', 'pending_new', 'accepted_for_bidding', 'new')]
        filled_orders = [o for o in orders if o.get('status') == 'filled']

        result = {
            "status": "ACTIVE",
            "is_fallback": False,
            "source_timestamp": now_iso,
            "source_timestamp_sec": int(now),
            "cache_age_sec": 0.0,
            "account_id": account.get('id'),
            "account": account,
            "positions_count": len(positions),
            "total_unrealized_pl": round(total_unrealized_pl, 4),
            "total_unrealized_plpc": round(unrealized_plpc, 4),
            "total_cost_basis": round(total_cost_basis, 2),
            "open_orders_count": len(open_orders),
            "filled_orders_count": len(filled_orders),
            "recent_orders_count": len(orders),
            "positions": positions,
            "recent_orders": orders[:20]
        }

        # Update Last-Known-Good snapshot
        _LAST_KNOWN_GOOD_PORTFOLIO = dict(result)
        _LAST_KNOWN_GOOD_TIME = now_iso
        _LAST_KNOWN_GOOD_TS = now
        _PORTFOLIO_CACHE = result
        _PORTFOLIO_CACHE_TIME = now
        return result

    # Handled API Failure: Return Last-Known-Good if available, else error state
    error_msg = account.get('error', 'Alpaca API connection unreachable')
    if _LAST_KNOWN_GOOD_PORTFOLIO is not None:
        fallback = dict(_LAST_KNOWN_GOOD_PORTFOLIO)
        fallback['status'] = 'DEGRADED_LAST_KNOWN_GOOD'
        fallback['is_fallback'] = True
        fallback['fallback_reason'] = f"Alpaca API unavailable ({error_msg}). Showing last known good state."
        fallback['cache_age_sec'] = round(now - _LAST_KNOWN_GOOD_TS, 1)
        return fallback

    return {
        "status": "UNAVAILABLE",
        "is_fallback": False,
        "error": error_msg,
        "source_timestamp": now_iso,
        "source_timestamp_sec": int(now),
        "cache_age_sec": 0.0,
        "account_id": None,
        "account": None,
        "positions_count": 0,
        "total_unrealized_pl": 0.0,
        "total_unrealized_plpc": 0.0,
        "total_cost_basis": 0.0,
        "open_orders_count": 0,
        "filled_orders_count": 0,
        "recent_orders_count": 0,
        "positions": [],
        "recent_orders": []
    }
