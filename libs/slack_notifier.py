"""
slack_notifier.py — Production-Grade Slack Notification Engine for Stocks & Crypto.
Provides:
- Rich formatted Block Kit messages for BUY/SELL trading signals and order execution receipts.
- Clear distinction between Trading Signals and Alpaca Orders.
- Zero fabrication of missing fields (reports N/A cleanly).
- Transient error retry with exponential backoff (bounded up to 3 retries).
- HTTP 429 Rate-limit detection and Retry-After backoff.
- Persistent deduplication across process restarts (data/status/slack_notifications.json).
- Safe MOCK mode when Slack credentials are not configured or set to placeholders.
- Non-blocking error handling to ensure Signal Handlers never crash on network failure.
"""
import os
import sys
import time
import json
import logging
from typing import Dict, Any, Optional
import requests

# Base directories
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
STATUS_DIR = os.path.join(DATA_DIR, 'status')
os.makedirs(STATUS_DIR, exist_ok=True)

DEFAULT_STATE_FILE = os.path.join(STATUS_DIR, 'slack_notifications.json')
MOCK_LOG_FILE = os.path.join(STATUS_DIR, 'slack_mock_notifications.jsonl')
OUTBOX_FILE = os.path.join(STATUS_DIR, 'slack_outbox.jsonl')
DEAD_LETTER_FILE = os.path.join(STATUS_DIR, 'slack_dead_letter.jsonl')

logger = logging.getLogger('slack-notifier')

class SlackNotifier:
    def __init__(
        self,
        token: Optional[str] = None,
        channel_id: Optional[str] = None,
        state_file: Optional[str] = None,
        max_retries: int = 3,
        session: Optional[requests.Session] = None
    ):
        self.state_file = state_file or DEFAULT_STATE_FILE
        self.max_retries = max_retries
        self.session = session or requests.Session()
        
        # Load credentials if not provided
        if token is None or channel_id is None:
            try:
                from alpaca_config.keys import config
                self.token = token or config.get('slack_token', os.environ.get('SLACK_BOT_TOKEN', '')).strip()
                self.channel_id = channel_id or config.get('slack_channel_id', os.environ.get('SLACK_CHANNEL_ID', '')).strip()
            except ImportError:
                self.token = token or os.environ.get('SLACK_BOT_TOKEN', '').strip()
                self.channel_id = channel_id or os.environ.get('SLACK_CHANNEL_ID', '').strip()
        else:
            self.token = token.strip()
            self.channel_id = channel_id.strip()

        # Check if credentials are real or placeholder
        self.is_configured = self._check_is_configured(self.token, self.channel_id)
        
        # In-memory and persistent delivered signal registry
        self.delivered_signals: Dict[str, Any] = self._load_state()

    @staticmethod
    def _check_is_configured(token: str, channel_id: str) -> bool:
        if not token or not channel_id:
            return False
        # Placeholder patterns
        placeholders = [
            'YOUR-SLACK-BOT-TOKEN-HERE',
            'YOUR_SLACK_BOT_TOKEN_HERE',
            'YOUR-CHANNEL-ID-HERE',
            'YOUR_CHANNEL_ID_HERE',
            'xoxb-YOUR'
        ]
        for p in placeholders:
            if p in token or p in channel_id:
                return False
        return token.startswith('xoxb-') or token.startswith('xoxp-')

    def _load_state(self) -> Dict[str, Any]:
        """Loads delivered signal keys from persistent JSON state file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info("Loaded %d previously delivered Slack notification keys from %s", len(data), self.state_file)
                    return data
            except Exception as e:
                logger.warning("Could not read Slack notification state file (%s): %s", self.state_file, e)
        return {}

    def _save_state(self):
        """Atomically saves delivered signals state."""
        try:
            temp_file = self.state_file + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.delivered_signals, f, indent=2)
            os.replace(temp_file, self.state_file)
        except Exception as e:
            logger.error("Failed to persist Slack notification state: %s", e)

    def test_auth(self) -> Dict[str, Any]:
        """Tests Slack Bot authentication via auth.test."""
        if not self.is_configured:
            return {'ok': False, 'error': 'NOT_CONFIGURED', 'message': 'Slack credentials missing or placeholder in .env'}
        
        try:
            resp = requests.post(
                'https://slack.com/api/auth.test',
                headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'},
                timeout=8
            )
            data = resp.json()
            return data
        except Exception as e:
            logger.error("Slack auth.test network failure: %s", e)
            return {'ok': False, 'error': 'NETWORK_ERROR', 'message': str(e)}

    def test_channel_access(self) -> Dict[str, Any]:
        """Verifies bot has access to target channel via conversations.info."""
        if not self.is_configured:
            return {'ok': False, 'error': 'NOT_CONFIGURED', 'message': 'Slack credentials missing or placeholder'}

        try:
            resp = requests.get(
                'https://slack.com/api/conversations.info',
                headers={'Authorization': f'Bearer {self.token}'},
                params={'channel': self.channel_id},
                timeout=8
            )
            return resp.json()
        except Exception as e:
            logger.error("Slack conversations.info network failure: %s", e)
            return {'ok': False, 'error': 'NETWORK_ERROR', 'message': str(e)}

    def build_signal_payload(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Builds standardized Slack Block Kit payload for Trading Signals.
        Distinguishes between BUY and SELL.
        Never fabricates missing fields.
        """
        asset_type = str(signal_data.get('asset_type', 'stocks')).lower()
        symbol = str(signal_data.get('symbol', 'N/A')).upper()
        signal_type = str(signal_data.get('signal', 'N/A')).upper()
        signal_time = str(signal_data.get('signal_time', 'N/A'))
        trading_mode = str(signal_data.get('trading_mode', 'DRY_RUN')).upper()

        price_val = signal_data.get('price')
        price_str = f"${float(price_val):,.2f}" if price_val is not None and price_val != 'N/A' else "N/A"

        sma20_val = signal_data.get('sma_20')
        sma20_str = f"${float(sma20_val):,.2f}" if sma20_val is not None and sma20_val != 'N/A' else "N/A"

        sma50_val = signal_data.get('sma_50')
        sma50_str = f"${float(sma50_val):,.2f}" if sma50_val is not None and sma50_val != 'N/A' else "N/A"

        sent_val = signal_data.get('sentiment')
        sent_str = f"{float(sent_val):+.4f}" if sent_val is not None and sent_val != 'N/A' else "N/A"

        # Unique Signal ID
        signal_id = signal_data.get('signal_id')
        if not signal_id:
            safe_sym = symbol.replace('/', '')
            safe_time = signal_time.replace(' ', '_').replace(':', '')
            signal_id = f"SIG-{asset_type.upper()}-{safe_sym}-{signal_type}-{safe_time}"

        # Color and Emoji
        if signal_type == 'BUY':
            header_emoji = "🟢"
            action_text = "BUY SIGNAL"
        elif signal_type == 'SELL':
            header_emoji = "🔴"
            action_text = "SELL SIGNAL"
        else:
            header_emoji = "⚠️"
            action_text = f"SIGNAL ({signal_type})"

        fallback_text = f"[{trading_mode}] {header_emoji} {action_text}: {symbol} ({asset_type.upper()}) at {signal_time} | Ref Price: {price_str}"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{header_emoji} Trading Signal Alert: {symbol} — {action_text}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Asset Type:*\n`{asset_type.upper()}`"},
                    {"type": "mrkdwn", "text": f"*Symbol:*\n*{symbol}*"},
                    {"type": "mrkdwn", "text": f"*Signal Side:*\n*{signal_type}*"},
                    {"type": "mrkdwn", "text": f"*Trading Mode:*\n`{trading_mode}`"},
                    {"type": "mrkdwn", "text": f"*Reference Price:*\n{price_str}"},
                    {"type": "mrkdwn", "text": f"*Sentiment Score:*\n{sent_str}"},
                    {"type": "mrkdwn", "text": f"*SMA 20:*\n{sma20_str}"},
                    {"type": "mrkdwn", "text": f"*SMA 50:*\n{sma50_str}"}
                ]
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"⏱️ *Signal Time:* `{signal_time}` | 🆔 *Signal ID:* `{signal_id}`"},
                    {"type": "mrkdwn", "text": "🤖 *Strategy:* SMA20 Crossover + VADER Sentiment Stream"}
                ]
            },
            {"type": "divider"}
        ]

        return {
            'channel': self.channel_id,
            'text': fallback_text,
            'blocks': blocks,
            'metadata': {
                'signal_id': signal_id,
                'symbol': symbol,
                'signal': signal_type,
                'signal_time': signal_time,
                'asset_type': asset_type,
                'trading_mode': trading_mode
            }
        }

    def build_order_payload(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Builds standardized Slack Block Kit payload for Alpaca Order confirmations.
        Explicitly clarifies that this is an ORDER EXECUTION, not a raw signal.
        """
        symbol = str(order_data.get('symbol', 'N/A')).upper()
        side = str(order_data.get('side', 'N/A')).upper()
        status = str(order_data.get('status', 'N/A')).upper()
        order_id = str(order_data.get('order_id', order_data.get('id', 'N/A')))
        client_order_id = str(order_data.get('client_order_id', 'N/A'))
        qty = order_data.get('qty', order_data.get('filled_qty', 'N/A'))
        price = order_data.get('filled_avg_price', 'N/A')
        price_str = f"${float(price):,.2f}" if price != 'N/A' and price is not None else "Pending"
        endpoint = order_data.get('endpoint', 'https://paper-api.alpaca.markets')
        is_paper = 'paper-api' in endpoint

        status_emoji = "✅" if status in ('FILLED', 'ACCEPTED', 'NEW') else "⚠️"
        mode_str = "ALPACA PAPER TRADING" if is_paper else "LIVE TRADING"

        fallback_text = f"{status_emoji} [{mode_str}] Order {status}: {side} {qty} {symbol} (Order ID: {order_id})"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji} Alpaca Order Execution: {symbol} — {status}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Environment:*\n`{mode_str}`"},
                    {"type": "mrkdwn", "text": f"*Symbol:*\n*{symbol}*"},
                    {"type": "mrkdwn", "text": f"*Side:*\n*{side}*"},
                    {"type": "mrkdwn", "text": f"*Status:*\n`{status}`"},
                    {"type": "mrkdwn", "text": f"*Quantity:*\n`{qty}`"},
                    {"type": "mrkdwn", "text": f"*Fill Avg Price:*\n{price_str}"}
                ]
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"📋 *Order ID:* `{order_id}` | 🔖 *Client ID:* `{client_order_id}`"}
                ]
            },
            {"type": "divider"}
        ]

        return {
            'channel': self.channel_id,
            'text': fallback_text,
            'blocks': blocks
        }

    def _post_with_retry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executes chat.postMessage with exponential backoff and 429 Retry-After handling."""
        url = 'https://slack.com/api/chat.postMessage'
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json; charset=utf-8'
        }

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.post(url, headers=headers, json=payload, timeout=8)
                
                # Check HTTP 429 Rate Limit
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get('Retry-After', 2))
                    logger.warning("Slack rate limit (429) hit. Backing off for %d seconds (attempt %d/%d)", retry_after, attempt, self.max_retries)
                    time.sleep(min(retry_after, 5))
                    continue

                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}: {resp.text}"
                    logger.warning("Slack API HTTP error on attempt %d/%d: %s", attempt, self.max_retries, last_error)
                    time.sleep(attempt * 1.5)
                    continue

                data = resp.json()
                if data.get('ok'):
                    return {'ok': True, 'ts': data.get('ts'), 'channel': data.get('channel')}
                else:
                    last_error = data.get('error', 'unknown_slack_error')
                    logger.error("Slack API error: %s (attempt %d/%d)", last_error, attempt, self.max_retries)
                    # Non-retriable Slack errors
                    if last_error in ('channel_not_found', 'invalid_auth', 'not_in_channel', 'account_inactive'):
                        return {'ok': False, 'error': last_error, 'retriable': False}
                    time.sleep(attempt * 1.5)

            except requests.RequestException as exc:
                last_error = str(exc)
                logger.warning("Slack network exception on attempt %d/%d: %s", attempt, self.max_retries, last_error)
                time.sleep(attempt * 1.5)

        return {'ok': False, 'error': last_error or 'MAX_RETRIES_EXCEEDED', 'retriable': True}

    def send_signal_notification(self, signal_data: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        """
        Sends formatted trading signal alert to Slack with full deduplication, outbox logging, and error handling.
        Returns detailed dispatch result dict.
        """
        payload = self.build_signal_payload(signal_data)
        meta = payload.get('metadata', {})
        signal_id = meta.get('signal_id', 'UNKNOWN')
        dedup_key = f"{meta.get('asset_type')}:{meta.get('symbol')}:{meta.get('signal')}:{meta.get('signal_time')}"

        # 1. Deduplication check
        if not force and (signal_id in self.delivered_signals or dedup_key in self.delivered_signals):
            logger.info("Slack notification skipped: Duplicate signal key '%s'", dedup_key)
            return {'status': 'SKIPPED_DUPLICATE', 'signal_id': signal_id, 'dedup_key': dedup_key}

        # Outbox entry
        outbox_entry = {
            'timestamp': time.time(),
            'iso_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'signal_id': signal_id,
            'dedup_key': dedup_key,
            'status': 'PENDING'
        }
        try:
            with open(OUTBOX_FILE, 'a', encoding='utf-8') as ob:
                ob.write(json.dumps(outbox_entry) + '\n')
        except Exception:
            pass

        # 2. Mock mode if not configured
        if not self.is_configured:
            logger.info("[MOCK_SLACK] Bot credentials not active. Mock dispatch for signal %s:\n%s", signal_id, payload['text'])
            mock_entry = {
                'timestamp': time.time(),
                'iso_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'signal_id': signal_id,
                'dedup_key': dedup_key,
                'payload': payload,
                'status': 'MOCK_DELIVERED'
            }
            try:
                with open(MOCK_LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(mock_entry) + '\n')
            except Exception:
                pass

            self.delivered_signals[signal_id] = {'status': 'MOCK_DELIVERED', 'timestamp': time.time()}
            self.delivered_signals[dedup_key] = {'status': 'MOCK_DELIVERED', 'timestamp': time.time()}
            self._save_state()
            return {'status': 'MOCK_DELIVERED', 'signal_id': signal_id, 'dedup_key': dedup_key}

        # 3. Real Slack dispatch
        res = self._post_with_retry(payload)
        if res.get('ok'):
            logger.info("Successfully delivered Slack notification for %s (ts=%s)", signal_id, res.get('ts'))
            record = {
                'status': 'DELIVERED',
                'ts': res.get('ts'),
                'channel': res.get('channel'),
                'timestamp': time.time(),
                'iso_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'symbol': meta.get('symbol'),
                'signal': meta.get('signal')
            }
            self.delivered_signals[signal_id] = record
            self.delivered_signals[dedup_key] = record
            self._save_state()

            # Update outbox
            outbox_entry['status'] = 'DELIVERED'
            outbox_entry['slack_ts'] = res.get('ts')
            try:
                with open(OUTBOX_FILE, 'a', encoding='utf-8') as ob:
                    ob.write(json.dumps(outbox_entry) + '\n')
            except Exception:
                pass

            return {'status': 'DELIVERED', 'signal_id': signal_id, 'slack_ts': res.get('ts')}
        else:
            logger.error("Failed to deliver Slack notification for %s: %s", signal_id, res.get('error'))
            # Dead letter queue entry
            dead_letter_entry = {
                'timestamp': time.time(),
                'iso_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'signal_id': signal_id,
                'dedup_key': dedup_key,
                'payload': payload,
                'error': res.get('error'),
                'retriable': res.get('retriable', True),
                'status': 'FAILED_PERMANENT' if not res.get('retriable', True) else 'FAILED_TRANSIENT'
            }
            try:
                with open(DEAD_LETTER_FILE, 'a', encoding='utf-8') as df:
                    df.write(json.dumps(dead_letter_entry) + '\n')
            except Exception:
                pass

            return {'status': 'FAILED', 'signal_id': signal_id, 'error': res.get('error'), 'dead_letter': True}

    def send_order_notification(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sends order execution confirmation notification."""
        payload = self.build_order_payload(order_data)
        order_id = str(order_data.get('order_id', order_data.get('id', 'UNKNOWN')))

        if not self.is_configured:
            logger.info("[MOCK_SLACK] Mock order dispatch:\n%s", payload['text'])
            return {'status': 'MOCK_DELIVERED', 'order_id': order_id}

        res = self._post_with_retry(payload)
        if res.get('ok'):
            return {'status': 'DELIVERED', 'order_id': order_id, 'slack_ts': res.get('ts')}
        else:
            return {'status': 'FAILED', 'order_id': order_id, 'error': res.get('error')}

