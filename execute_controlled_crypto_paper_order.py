"""
execute_controlled_crypto_paper_order.py — Controlled Single-Shot Alpaca Crypto Paper Order Execution.
Strictly adheres to safety constraints:
- Max 1 order only.
- Strict validation of symbol, side, notional, and paper endpoint.
- Query before and after portfolio & position.
- Save receipt to data/orders/gd10_6_paper_order_receipt.json.
"""
import os
import sys
import time
import json
import requests
from datetime import datetime, timezone

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LIBS_DIR = os.path.join(BASE_DIR, 'libs')
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

from alpaca_config.keys import config

PAPER_BASE_URL = config.get('trade_api_base_url', 'https://paper-api.alpaca.markets')
RECEIPT_FILE = os.path.join(BASE_DIR, 'data', 'orders', 'gd10_6_paper_order_receipt.json')

def get_headers():
    return {
        'APCA-API-KEY-ID': config['key_id'],
        'APCA-API-SECRET-KEY': config['secret_key'],
        'Content-Type': 'application/json'
    }

def verify_paper_endpoint():
    if 'paper-api' not in PAPER_BASE_URL:
        raise RuntimeError(f"FATAL SAFETY VIOLATION: Endpoint {PAPER_BASE_URL} is NOT a paper trading URL!")

def get_account():
    r = requests.get(f"{PAPER_BASE_URL}/v2/account", headers=get_headers(), timeout=5)
    r.raise_for_status()
    return r.json()

def get_position(symbol: str):
    clean = symbol.replace('/', '')
    r = requests.get(f"{PAPER_BASE_URL}/v2/positions/{clean}", headers=get_headers(), timeout=5)
    if r.status_code == 200:
        return r.json()
    return None

def execute_single_paper_order(symbol: str, side: str, notional: float, order_type: str = 'market', max_orders: int = 1):
    verify_paper_endpoint()
    if max_orders != 1:
        raise ValueError(f"Safety restriction violated: max_orders must be exactly 1, got {max_orders}")

    clean_symbol = symbol.replace('/', '')
    if clean_symbol not in ('BTCUSD', 'ETHUSD'):
        raise ValueError(f"Unsupported crypto test symbol: {clean_symbol}")

    side = side.lower()
    if side not in ('buy', 'sell'):
        raise ValueError(f"Invalid order side: {side}")

    notional = round(float(notional), 2)
    if notional <= 0 or notional > 50.0:
        raise ValueError(f"Notional USD must be between $1.00 and $50.00, got ${notional}")

    print("=" * 60)
    print("CONTROLLED ALPACAPAPER CRYPTO ORDER SUBMISSION")
    print("=" * 60)

    # 1. Pre-execution checks
    account_pre = get_account()
    pos_pre = get_position(clean_symbol)
    print(f"Account Status: {account_pre.get('status')} | Cash: ${account_pre.get('cash')} | Buying Power: ${account_pre.get('buying_power')}")
    pos_pre_qty = pos_pre.get('qty', '0.0') if pos_pre else '0.0'
    print(f"Pre-order Position for {clean_symbol}: {pos_pre_qty} units")

    # 2. Prepare payload
    client_order_id = f"GD10-6-TEST-{clean_symbol}-{side.upper()}-{int(time.time())}"
    payload = {
        'symbol': clean_symbol,
        'side': side,
        'type': order_type,
        'time_in_force': 'gtc',
        'notional': notional,
        'client_order_id': client_order_id
    }
    print(f"Submitting 1 test order to Alpaca Paper API:\n  {payload}")

    # 3. Submit Order
    resp = requests.post(f"{PAPER_BASE_URL}/v2/orders", headers=get_headers(), json=payload, timeout=10)
    if resp.status_code not in (200, 201):
        err_msg = f"Order submission failed (HTTP {resp.status_code}): {resp.text}"
        print(f"ERROR: {err_msg}")
        return {'status': 'FAILED', 'error': err_msg}

    order_data = resp.json()
    order_id = order_data.get('id')
    print(f"\nOrder Accepted! Order ID: {order_id} | Initial Status: {order_data.get('status')}")

    # 4. Poll for status
    final_status = order_data.get('status')
    for _ in range(6):
        time.sleep(2)
        try:
            r_ord = requests.get(f"{PAPER_BASE_URL}/v2/orders/{order_id}", headers=get_headers(), timeout=5)
            if r_ord.status_code == 200:
                ord_info = r_ord.json()
                final_status = ord_info.get('status')
                print(f"Polling status... Status: {final_status} | Filled Qty: {ord_info.get('filled_qty')}")
                if final_status in ('filled', 'canceled', 'rejected', 'expired'):
                    order_data = ord_info
                    break
        except Exception as e:
            print("Poll error:", e)

    # 5. Post-execution checks
    time.sleep(2)
    pos_post = get_position(clean_symbol)
    account_post = get_account()
    print(f"\nPost-order Position for {clean_symbol}: {pos_post.get('qty', '0.0') if pos_post else '0.0'} units")
    print(f"Post-order Cash: ${account_post.get('cash')}")

    receipt = {
        'execution_timestamp': datetime.now(timezone.utc).isoformat(),
        'endpoint': PAPER_BASE_URL,
        'symbol': clean_symbol,
        'side': side,
        'notional': notional,
        'order_type': order_type,
        'order_id': order_id,
        'client_order_id': client_order_id,
        'initial_status': order_data.get('status'),
        'final_status': final_status,
        'filled_qty': order_data.get('filled_qty'),
        'filled_avg_price': order_data.get('filled_avg_price'),
        'pre_position_qty': pos_pre.get('qty') if pos_pre else '0.0',
        'post_position_qty': pos_post.get('qty') if pos_post else '0.0',
        'portfolio_cash_pre': account_pre.get('cash'),
        'portfolio_cash_post': account_post.get('cash')
    }

    os.makedirs(os.path.dirname(RECEIPT_FILE), exist_ok=True)
    with open(RECEIPT_FILE, 'w', encoding='utf-8') as f:
        json.dump(receipt, f, indent=2)

    print(f"\nReceipt saved to: {RECEIPT_FILE}")
    return receipt

if __name__ == '__main__':
    # Default parameters for test order
    symbol = sys.argv[1] if len(sys.argv) > 1 else 'BTCUSD'
    side = sys.argv[2] if len(sys.argv) > 2 else 'buy'
    notional = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
    execute_single_paper_order(symbol=symbol, side=side, notional=notional, order_type='market', max_orders=1)
