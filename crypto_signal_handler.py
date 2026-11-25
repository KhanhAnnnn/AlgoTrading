"""
crypto_signal_handler.py — Safe Production Crypto Trading Signal Consumer & Paper Execution Guard
Consumes BUY/SELL signals from 'crypto-signals' topic, enforces strict schema validation & deduplication,
maintains persistent order-intent state, enforces position and buying power safeguards,
and operates in DRY_RUN mode by default (asserting https://paper-api.alpaca.markets).
"""
import os
import sys
import time
import json
import signal
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Set, List
import psutil
import requests
from kafka import KafkaConsumer

# Include libs in path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LIBS_DIR = os.path.join(BASE_DIR, 'libs')
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

from alpaca_config.keys import config
from slack_notifier import SlackNotifier
from shadow_mode_observer import shadow_observer

# Directories
DATA_DIR = os.path.join(BASE_DIR, 'data')
ORDERS_DIR = os.path.join(DATA_DIR, 'orders')
LOCK_DIR = os.path.join(DATA_DIR, 'locks')
STATUS_DIR = os.path.join(DATA_DIR, 'status')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

for d in [ORDERS_DIR, LOCK_DIR, STATUS_DIR, LOGS_DIR]:
    os.makedirs(d, exist_ok=True)

PID_FILE = os.path.join(LOCK_DIR, 'crypto_signal_handler.pid')
ORDER_INTENT_FILE = os.path.join(ORDERS_DIR, 'crypto_order_intent.json')
HEALTH_FILE = os.path.join(STATUS_DIR, 'crypto_handler_health.json')
LOG_FILE = os.path.join(LOGS_DIR, 'crypto_signal_handler.log')

# Logging
logger = logging.getLogger('crypto-signal-handler')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s (PID %(process)d): %(message)s')

logger.handlers.clear()
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
logger.addHandler(ch)

fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
fh.setFormatter(formatter)
logger.addHandler(fh)

TRADING_MODE = os.environ.get('TRADING_MODE', 'DRY_RUN').upper()
PAPER_BASE_URL = config.get('trade_api_base_url', 'https://paper-api.alpaca.markets')
if 'paper-api' not in PAPER_BASE_URL:
    raise RuntimeError(f"CRITICAL SAFETY VIOLATION: '{PAPER_BASE_URL}' is not an Alpaca Paper Trading endpoint.")


class SingleInstanceLock:
    def __init__(self, pid_file: str):
        self.pid_file = pid_file

    def acquire(self):
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file, 'r') as f:
                    content = f.read().strip()
                if content:
                    old_pid = int(content)
                    if psutil.pid_exists(old_pid) and old_pid != os.getpid():
                        proc = psutil.Process(old_pid)
                        if 'python' in proc.name().lower():
                            logger.error("Another Crypto Signal Handler instance (PID %d) is already active.", old_pid)
                            sys.exit(1)
            except Exception:
                pass
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))

    def release(self):
        if os.path.exists(self.pid_file):
            try:
                os.remove(self.pid_file)
            except Exception:
                pass


class CryptoSignalHandler:
    ALLOWED_SYMBOLS = {'BTC/USD', 'ETH/USD', 'BTCUSD', 'ETHUSD'}
    MAX_NOTIONAL_USD = 100.0  # Max risk per test order $100

    def __init__(self, mode: Optional[str] = None):
        self.mode = (mode or TRADING_MODE).upper()
        self.running = False
        self.start_time = time.time()
        self.key_id = config.get('key_id')
        self.secret_key = config.get('secret_key')

        env_brokers = os.environ.get('REDPANDA_BROKERS')
        if env_brokers:
            self.brokers = [b.strip() for b in env_brokers.split(',') if b.strip()]
        else:
            self.brokers = config.get('redpanda_brokers', ['localhost:9092', 'localhost:9093'])

        self.processed_signals: Set[str] = set()
        self.order_intents: List[Dict[str, Any]] = self._load_order_intents()
        self.slack_notifier = SlackNotifier()

    def _load_order_intents(self) -> List[Dict[str, Any]]:
        if os.path.exists(ORDER_INTENT_FILE):
            try:
                with open(ORDER_INTENT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        k = f"{item.get('symbol')}:{item.get('signal')}:{item.get('signal_time')}"
                        self.processed_signals.add(k)
                    logger.info("Loaded %d existing crypto order intents.", len(data))
                    return data
            except Exception as e:
                logger.warning("Failed to load order intents: %s", e)
        return []

    def _save_order_intents(self):
        try:
            temp_file = ORDER_INTENT_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.order_intents[-500:], f, indent=2)
            os.replace(temp_file, ORDER_INTENT_FILE)
        except Exception as e:
            logger.error("Failed to save crypto order intents: %s", e)

    def _get_headers(self) -> Dict[str, str]:
        return {
            'APCA-API-KEY-ID': self.key_id,
            'APCA-API-SECRET-KEY': self.secret_key,
            'Content-Type': 'application/json'
        }

    def get_crypto_position(self, symbol: str) -> float:
        """Queries Alpaca Paper account for current crypto position qty."""
        clean_sym = symbol.replace('/', '')
        try:
            resp = requests.get(f"{PAPER_BASE_URL}/v2/positions/{clean_sym}", headers=self._get_headers(), timeout=5)
            if resp.status_code == 200:
                pos = resp.json()
                return float(pos.get('qty', 0.0))
        except Exception as e:
            logger.warning("Error fetching position for %s: %s", symbol, e)
        return 0.0

    def get_buying_power(self) -> float:
        """Queries Alpaca Paper account buying power."""
        try:
            resp = requests.get(f"{PAPER_BASE_URL}/v2/account", headers=self._get_headers(), timeout=5)
            if resp.status_code == 200:
                acc = resp.json()
                return float(acc.get('buying_power', 0.0))
        except Exception as e:
            logger.warning("Error fetching account buying power: %s", e)
        return 0.0

    def check_existing_order_by_client_id(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        """Looks up existing order by client_order_id to prevent duplicate submissions."""
        try:
            resp = requests.get(
                f"{PAPER_BASE_URL}/v2/orders:by_client_order_id?client_order_id={client_order_id}",
                headers=self._get_headers(),
                timeout=5
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def execute_paper_order(
        self,
        symbol: str,
        side: str,
        qty: Optional[float] = None,
        notional: Optional[float] = None,
        client_order_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Submits paper trading order to Alpaca Paper API."""
        if 'paper-api' not in PAPER_BASE_URL:
            raise RuntimeError("SAFETY ASSERTION: Live trading disallowed!")

        clean_sym = symbol.replace('/', '')
        order_payload = {
            'symbol': clean_sym,
            'side': side.lower(),
            'type': 'market',
            'time_in_force': 'gtc'
        }
        if notional:
            order_payload['notional'] = round(float(notional), 2)
        elif qty:
            order_payload['qty'] = round(float(qty), 6)

        if client_order_id:
            order_payload['client_order_id'] = client_order_id

        logger.info("[PAPER_TRADING] Submitting order payload: %s", order_payload)

        try:
            resp = requests.post(f"{PAPER_BASE_URL}/v2/orders", headers=self._get_headers(), json=order_payload, timeout=8)
            if resp.status_code in (200, 201):
                order_data = resp.json()
                logger.info("Order accepted by Alpaca: id=%s, client_order_id=%s, status=%s",
                            order_data.get('id'), order_data.get('client_order_id'), order_data.get('status'))
                return order_data
            else:
                logger.error("Alpaca order rejected (HTTP %s): %s", resp.status_code, resp.text)
                return None
        except Exception as exc:
            logger.error("Failed to submit paper order: %s", exc)
            return None

    def process_signal(self, raw_msg: str) -> Optional[Dict[str, Any]]:
        """Validates, deduplicates, and executes/dry-runs crypto trading signal."""
        try:
            sig_dict = json.loads(raw_msg)
        except Exception as exc:
            logger.error("JSON decode error on crypto signal: %s", exc)
            return None

        symbol = str(sig_dict.get('symbol', '')).upper()
        signal_type = str(sig_dict.get('signal', '')).upper()
        sig_time = str(sig_dict.get('signal_time', ''))
        price = float(sig_dict.get('price', 0.0))
        sentiment = float(sig_dict.get('sentiment', 0.0))
        sma_20 = float(sig_dict.get('sma_20', 0.0))
        sma_50 = float(sig_dict.get('sma_50', 0.0))

        # 1. Validation
        if symbol not in self.ALLOWED_SYMBOLS:
            logger.warning("Rejected signal for unauthorized symbol: %s", symbol)
            return None

        if signal_type not in ('BUY', 'SELL'):
            logger.warning("Rejected signal with unknown side: %s", signal_type)
            return None

        # 2. Deduplication Key
        dedup_key = f"{symbol}:{signal_type}:{sig_time}"
        is_fixture = bool(sig_dict.get('is_test_fixture', False) or 'TEST' in symbol)
        if dedup_key in self.processed_signals:
            logger.info("Duplicate crypto signal detected, skipping: %s", dedup_key)
            shadow_observer.record_observation(
                symbol=symbol,
                signal_type=signal_type,
                event_time=sig_time,
                price=price,
                sentiment=sentiment,
                sma_20=sma_20,
                sma_50=sma_50,
                is_fixture=is_fixture,
            )
            return None

        self.processed_signals.add(dedup_key)

        # Record in Shadow Mode Observer (Read-Only)
        shadow_observer.record_observation(
            symbol=symbol,
            signal_type=signal_type,
            event_time=sig_time,
            price=price,
            sentiment=sentiment,
            sma_20=sma_20,
            sma_50=sma_50,
            is_fixture=is_fixture,
        )

        # 3. Form stable deterministic client order ID
        clean_sym = symbol.replace('/', '').replace(':', '')
        safe_sig_time = str(sig_time).replace(' ', '_').replace(':', '').replace('-', '').replace('.', '')
        client_order_id = f"CRYPTO-{clean_sym}-{signal_type}-{safe_sig_time[:16]}"

        # 4. Safeguard & Notional sizing
        # For BTC ($80,000+), sizing $50 notional or 0.0005 BTC
        # For ETH ($2,400+), sizing $50 notional or 0.02 ETH
        notional_usd = min(50.0, self.MAX_NOTIONAL_USD)

        intent = {
            'dedup_key': dedup_key,
            'client_order_id': client_order_id,
            'symbol': symbol,
            'signal': signal_type,
            'signal_time': sig_time,
            'price': price,
            'sentiment': sentiment,
            'sma_20': sma_20,
            'sma_50': sma_50,
            'notional_usd': notional_usd,
            'mode': self.mode,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'executed': False,
            'order_result': None,
        }

        logger.info("=" * 50)
        logger.info("VALIDATED CRYPTO SIGNAL: %s %s @ $%.2f | Sentiment: %.4f | SMA20: %.2f",
                    signal_type, symbol, price, sentiment, sma_20)
        logger.info("Mode: %s | ClientOrderID: %s", self.mode, client_order_id)
        logger.info("=" * 50)

        # Trigger rich Slack Trading Signal notification (non-blocking, fail-safe)
        try:
            self.slack_notifier.send_signal_notification({
                'asset_type': 'crypto',
                'symbol': symbol,
                'signal': signal_type,
                'signal_time': sig_time,
                'price': price,
                'sentiment': sentiment,
                'sma_20': sma_20,
                'sma_50': sma_50,
                'trading_mode': self.mode,
                'signal_id': client_order_id
            })
        except Exception as e:
            logger.warning("Slack notification non-fatal error: %s", e)

        # 5. Position & Balance validation
        if signal_type == 'SELL':
            current_pos = self.get_crypto_position(symbol)
            logger.info("[%s] Current open position: %f", symbol, current_pos)
            if current_pos <= 0.0:
                logger.warning("[%s] SELL signal rejected: No long position held (Shorting disallowed).", symbol)
                intent['rejection_reason'] = 'NO_POSITION_TO_SELL'
                self.order_intents.append(intent)
                self._save_order_intents()
                return intent

        if signal_type == 'BUY':
            buying_power = self.get_buying_power()
            logger.info("[%s] Account buying power: $%.2f (Required: $%.2f)", symbol, buying_power, notional_usd)
            if buying_power < notional_usd:
                logger.warning("[%s] BUY signal rejected: Insufficient buying power.", symbol)
                intent['rejection_reason'] = 'INSUFFICIENT_BUYING_POWER'
                self.order_intents.append(intent)
                self._save_order_intents()
                return intent

        # 6. Execution Branch
        if self.mode == 'DRY_RUN':
            logger.info("[DRY_RUN] Signal recorded. ZERO actual orders submitted to Alpaca.")
            intent['executed'] = False
            intent['order_result'] = {'status': 'DRY_RUN_SIMULATED', 'notional': notional_usd}
            self.order_intents.append(intent)
            self._save_order_intents()
            return intent

        if self.mode == 'PAPER_TRADING':
            # Check if order already submitted previously
            existing = self.check_existing_order_by_client_id(client_order_id)
            if existing:
                logger.warning("Order with client_order_id %s already exists. Skipping submit.", client_order_id)
                intent['order_result'] = existing
            else:
                order = self.execute_paper_order(
                    symbol=symbol,
                    side=signal_type,
                    notional=notional_usd,
                    client_order_id=client_order_id
                )
                intent['executed'] = bool(order)
                intent['order_result'] = order
                if order:
                    try:
                        self.slack_notifier.send_order_notification({
                            'symbol': symbol,
                            'side': signal_type,
                            'qty': order.get('qty', notional_usd),
                            'order_id': order.get('id'),
                            'client_order_id': client_order_id,
                            'status': order.get('status'),
                            'filled_avg_price': order.get('filled_avg_price'),
                            'endpoint': PAPER_BASE_URL
                        })
                    except Exception as e:
                        logger.warning("Slack order notification error: %s", e)

            self.order_intents.append(intent)
            self._save_order_intents()
            return intent

        return intent

    def _update_health(self, status: str = "RUNNING"):
        try:
            health = {
                'status': status,
                'pid': os.getpid(),
                'uptime_sec': int(time.time() - self.start_time),
                'trading_mode': self.mode,
                'total_order_intents': len(self.order_intents),
                'last_heartbeat': datetime.now(timezone.utc).isoformat(),
            }
            temp_file = HEALTH_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(health, f, indent=2)
            os.replace(temp_file, HEALTH_FILE)
        except Exception as e:
            logger.debug("Failed to write crypto handler health: %s", e)

    def start(self):
        self.running = True
        logger.info("Starting Crypto Signal Handler consumer on 'crypto-signals'...")
        logger.info("Mode: %s | Brokers: %s", self.mode, self.brokers)
        self._update_health("RUNNING")

        consumer = KafkaConsumer(
            'crypto-signals',
            bootstrap_servers=self.brokers,
            group_id='crypto-signal-handler-group',
            auto_offset_reset='earliest',
            enable_auto_commit=False,
            value_deserializer=lambda b: b.decode('utf-8', errors='replace'),
            consumer_timeout_ms=1000
        )

        last_hb = time.time()
        try:
            while self.running:
                for record in consumer:
                    if not self.running:
                        break
                    try:
                        self.process_signal(record.value)
                        consumer.commit()
                    except Exception as e:
                        logger.error("Error processing crypto signal record: %s", e)

                now = time.time()
                if now - last_hb >= 5.0:
                    self._update_health("RUNNING")
                    last_hb = now

                time.sleep(0.1)
        finally:
            consumer.close()
            self._update_health("STOPPED")
            logger.info("Crypto Signal Handler closed.")

    def stop(self):
        self.running = False


def main():
    lock = SingleInstanceLock(PID_FILE)
    lock.acquire()

    handler = CryptoSignalHandler()

    def handle_signal(sig, frame):
        logger.info("Termination signal (%d) received.", sig)
        handler.stop()
        lock.release()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        handler.start()
    finally:
        lock.release()


if __name__ == '__main__':
    main()
