"""
signal-handler.py  — Trading Signal Handler
Reads from Redpanda topic 'trading-signals' via kafka-python,
sends Slack notifications, and optionally submits paper trading orders.

Operating modes (set via environment variable TRADING_MODE):
  DRY_RUN        — log only, no orders submitted (DEFAULT, SAFE)
  PAPER_TRADING  — submit orders to Alpaca Paper Trading endpoint

IMPORTANT: Paper Trading only activates when:
  1. TRADING_MODE=PAPER_TRADING is explicitly set
  2. ALPACA_TRADE_BASE_URL contains 'paper-api.alpaca.markets'
  3. Both Alpaca credentials are present
"""

import json
import logging
import os
import sys
import time
from typing import Optional

import requests
from kafka import KafkaConsumer

# Ensure libs/ is in path to load config and .env
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'libs'))
try:
    from alpaca_config.keys import config
except ImportError:
    config = {}

try:
    from slack_notifier import SlackNotifier
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'libs'))
    from slack_notifier import SlackNotifier

try:
    from shadow_mode_observer import shadow_observer
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'libs'))
    from shadow_mode_observer import shadow_observer

# ── Configuration ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('signal-handler')

TRADING_MODE = config.get('trading_mode', os.environ.get('TRADING_MODE', 'DRY_RUN')).upper()
REDPANDA_BROKERS = config.get('redpanda_brokers', os.environ.get('REDPANDA_BROKERS', 'localhost:9092,localhost:9093').split(','))
SLACK_BOT_TOKEN = config.get('slack_token', os.environ.get('SLACK_BOT_TOKEN', ''))
SLACK_CHANNEL_ID = config.get('slack_channel_id', os.environ.get('SLACK_CHANNEL_ID', ''))
ALPACA_KEY_ID = config.get('key_id', os.environ.get('ALPACA_KEY_ID', ''))
ALPACA_SECRET_KEY = config.get('secret_key', os.environ.get('ALPACA_SECRET_KEY', ''))
ALPACA_TRADE_BASE_URL = config.get('trade_api_base_url', os.environ.get('ALPACA_TRADE_BASE_URL', 'https://paper-api.alpaca.markets'))

slack_notifier = SlackNotifier()

# Safety guard: block live trading
if 'paper-api' not in ALPACA_TRADE_BASE_URL and TRADING_MODE == 'PAPER_TRADING':
    logger.critical(
        "BLOCKED: ALPACA_TRADE_BASE_URL does not contain 'paper-api'. "
        "Live trading is not permitted. Exiting."
    )
    sys.exit(1)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
ORDERS_DIR = os.path.join(BASE_DIR, 'data', 'orders')
os.makedirs(ORDERS_DIR, exist_ok=True)
STOCKS_PROCESSED_FILE = os.path.join(ORDERS_DIR, 'stocks_processed_signals.json')

def _load_processed_signals() -> set:
    if os.path.exists(STOCKS_PROCESSED_FILE):
        try:
            with open(STOCKS_PROCESSED_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info("Loaded %d previously processed stocks signals from %s", len(data), STOCKS_PROCESSED_FILE)
                return set(data)
        except Exception as e:
            logger.warning("Could not read stocks processed signals: %s", e)
    return set()

def _save_processed_signals(signals: set):
    try:
        temp_file = STOCKS_PROCESSED_FILE + '.tmp'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(list(signals), f, indent=2)
        os.replace(temp_file, STOCKS_PROCESSED_FILE)
    except Exception as e:
        logger.error("Failed to save stocks processed signals: %s", e)

# Track processed signal IDs to avoid duplicate orders (persisted across restarts)
_processed_signals: set = _load_processed_signals()


# ── Slack ──────────────────────────────────────────────────────────────────────
def send_to_slack(message: str) -> bool:
    """Send a plain text message to Slack. Returns True on success."""
    if not slack_notifier.is_configured:
        logger.warning("[MOCK] Slack credentials not configured. Message would be:\n%s", message)
        return False
    res = slack_notifier._post_with_retry({'channel': slack_notifier.channel_id, 'text': message})
    return bool(res.get('ok'))


# ── Alpaca Trading ─────────────────────────────────────────────────────────────
def place_paper_order(symbol: str, qty: int, side: str, client_order_id: Optional[str] = None) -> Optional[dict]:
    """Submit a paper trading order with idempotency check. Only called in PAPER_TRADING mode."""
    if not ALPACA_KEY_ID or not ALPACA_SECRET_KEY:
        logger.error("Cannot place order: Alpaca credentials missing.")
        return None

    headers = {
        'APCA-API-KEY-ID': ALPACA_KEY_ID,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY,
        'Content-Type': 'application/json',
    }

    # Idempotency check: query order by client_order_id first
    if client_order_id:
        try:
            chk = requests.get(
                f'{ALPACA_TRADE_BASE_URL}/v2/orders:by_client_order_id?client_order_id={client_order_id}',
                headers=headers, timeout=5
            )
            if chk.status_code == 200:
                existing = chk.json()
                logger.info("Order already exists on Alpaca: id=%s client_order_id=%s status=%s",
                            existing.get('id'), client_order_id, existing.get('status'))
                return existing
        except Exception as e:
            logger.debug("Idempotency lookup error: %s", e)

    url = f'{ALPACA_TRADE_BASE_URL}/v2/orders'
    payload = {
        'symbol': symbol,
        'qty': str(qty),
        'side': side.lower(),
        'type': 'market',
        'time_in_force': 'gtc',
    }
    if client_order_id:
        payload['client_order_id'] = client_order_id

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code in (200, 201):
            order = response.json()
            logger.info(
                "Order submitted | order_id=%s symbol=%s side=%s qty=%s status=%s",
                order.get('id'), symbol, side, qty, order.get('status')
            )
            return order
        else:
            logger.error(
                "Alpaca API error: status=%s body=%s",
                response.status_code, response.text[:500]
            )
            return None
    except Exception as exc:
        logger.error("Failed to submit order: %s", exc)
        return None


# ── Signal Processing ──────────────────────────────────────────────────────────
def process_signal(raw_message: str) -> None:
    """Parse and act on a trading signal."""
    logger.info("Received raw message: %s", raw_message)
    try:
        msg = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse message as JSON: %s | error: %s", raw_message[:200], exc)
        return

    symbol = msg.get('symbol', 'N/A')
    signal = str(msg.get('signal', '')).upper()
    signal_time = str(msg.get('signal_time', 'N/A'))

    # Deduplication key
    dedup_key = f"{symbol}:{signal}:{signal_time}"
    if dedup_key in _processed_signals:
        logger.warning("Duplicate signal detected, skipping: %s", dedup_key)
        shadow_observer.record_observation(
            symbol=symbol,
            signal_type=signal,
            event_time=signal_time,
            is_fixture=bool(msg.get('is_test_fixture', False) or symbol.startswith('TEST_')),
        )
        return
    _processed_signals.add(dedup_key)
    _save_processed_signals(_processed_signals)

    # Record in Shadow Mode Observer (Read-Only)
    shadow_observer.record_observation(
        symbol=symbol,
        signal_type=signal,
        event_time=signal_time,
        price=msg.get('price'),
        sentiment=msg.get('sentiment'),
        sma_20=msg.get('sma_20'),
        sma_50=msg.get('sma_50'),
        is_fixture=bool(msg.get('is_test_fixture', False) or symbol.startswith('TEST_')),
    )

    # Validate signal
    if signal not in ('BUY', 'SELL'):
        logger.warning("Unknown signal '%s' for %s — ignoring.", signal, symbol)
        return

    # Stable deterministic client order ID
    safe_sym = symbol.replace('/', '').replace(':', '')
    safe_time = str(signal_time).replace(' ', '_').replace(':', '').replace('-', '').replace('.', '')
    client_order_id = f"STOCKS-{safe_sym}-{signal}-{safe_time[:16]}"

    formatted_message = (
        f"\n============================="
        f"\n⚠️ ALERT: New Trading Signal!"
        f"\nSymbol:  {symbol}"
        f"\nSignal:  {signal}"
        f"\nTime:    {signal_time}"
        f"\nMode:    {TRADING_MODE}"
        f"\n============================="
    )
    logger.info(formatted_message)

    # Send rich Slack notification (fail-safe and non-blocking)
    signal_payload = {
        'asset_type': 'stocks',
        'symbol': symbol,
        'signal': signal,
        'signal_time': signal_time,
        'trading_mode': TRADING_MODE,
        'price': msg.get('price'),
        'sentiment': msg.get('sentiment'),
        'sma_20': msg.get('sma_20'),
        'sma_50': msg.get('sma_50'),
        'signal_id': client_order_id
    }
    slack_notifier.send_signal_notification(signal_payload)

    qty = int(os.environ.get('ORDER_QTY', 1))

    if TRADING_MODE == 'DRY_RUN':
        logger.info(
            "[DRY_RUN] Would place %s order: symbol=%s qty=%d — NO order submitted.",
            signal, symbol, qty
        )
        return

    if TRADING_MODE == 'PAPER_TRADING':
        if symbol.startswith('TEST_'):
            logger.info("[PAPER_TRADING] Test symbol %s detected — skipping Alpaca submission.", symbol)
            return

        logger.info(
            "[PAPER_TRADING] Placing %s order: symbol=%s qty=%d",
            signal, symbol, qty
        )
        order = place_paper_order(symbol=symbol, qty=qty, side=signal, client_order_id=client_order_id)
        if order:
            logger.info("Paper order confirmed: %s", order.get('id'))
            slack_notifier.send_order_notification({
                'symbol': symbol,
                'side': signal,
                'qty': qty,
                'order_id': order.get('id'),
                'client_order_id': order.get('client_order_id', client_order_id),
                'status': order.get('status'),
                'filled_avg_price': order.get('filled_avg_price'),
                'endpoint': ALPACA_TRADE_BASE_URL
            })
        else:
            logger.error("Order submission failed for signal: %s", dedup_key)


# ── Main Consumer Loop ─────────────────────────────────────────────────────────
def main():
    logger.info("=" * 60)
    logger.info("Signal Handler Starting")
    logger.info("Mode: %s", TRADING_MODE)
    logger.info("Brokers: %s", REDPANDA_BROKERS)
    logger.info("Slack configured: %s", bool(SLACK_BOT_TOKEN and SLACK_CHANNEL_ID))
    logger.info("Trade endpoint: %s", ALPACA_TRADE_BASE_URL)
    logger.info("=" * 60)

    consumer_timeout_raw = os.environ.get('CONSUMER_TIMEOUT_MS', '')
    consumer_kwargs = {
        'bootstrap_servers': REDPANDA_BROKERS,
        'group_id': os.environ.get('KAFKA_GROUP_ID', 'signal-handler-group'),
        'auto_offset_reset': 'earliest',
        'enable_auto_commit': False,
        'value_deserializer': lambda b: b.decode('utf-8', errors='replace'),
    }
    if consumer_timeout_raw and int(consumer_timeout_raw) > 0:
        consumer_kwargs['consumer_timeout_ms'] = int(consumer_timeout_raw)

    consumer = KafkaConsumer(
        'trading-signals',
        **consumer_kwargs
    )

    logger.info("Consumer connected. Waiting for signals on 'trading-signals'...")

    try:
        for record in consumer:
            try:
                process_signal(record.value)
                consumer.commit()
            except Exception as exc:
                logger.error(
                    "Unhandled error processing record at offset %d: %s",
                    record.offset, exc, exc_info=True
                )
            time.sleep(0.1)  # small throttle
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    finally:
        consumer.close()
        logger.info("Consumer closed.")


if __name__ == '__main__':
    main()