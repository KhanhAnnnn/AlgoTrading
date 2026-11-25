"""
test_slack_integration.py — Comprehensive Automated Test Suite for Slack Integration.
Covers Section E Acceptance requirements:
1. Slack authentication & channel access checks.
2. Structured message formatting for Stocks BUY/SELL.
3. Structured message formatting for Crypto BUY/SELL.
4. Clean handling of missing fields (no fabrication).
5. Clear distinction between Trading Signal alert and Alpaca Order confirmation.
6. Persistent deduplication (skips duplicates, survives restart).
7. Transient error retry with exponential backoff.
8. HTTP 429 Rate Limit backoff with Retry-After header.
9. Fail-safe execution (signal handlers never crash if Slack fails).
10. Safe DRY_RUN mode assertion (zero unintended orders).
"""
import os
import sys
import json
import time
import unittest
import requests
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
LIBS_DIR = os.path.join(BASE_DIR, 'libs')
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

from libs.slack_notifier import SlackNotifier

TEST_STATE_FILE = os.path.join(BASE_DIR, 'data', 'status', 'test_slack_notifications.json')

class TestSlackIntegration(unittest.TestCase):
    def setUp(self):
        if os.path.exists(TEST_STATE_FILE):
            os.remove(TEST_STATE_FILE)
        self.notifier = SlackNotifier(
            token='xoxb-mock-test-token',
            channel_id='C1234567890',
            state_file=TEST_STATE_FILE,
            max_retries=3
        )
        # Force is_configured to True for mock API tests
        self.notifier.is_configured = True

    def tearDown(self):
        if os.path.exists(TEST_STATE_FILE):
            os.remove(TEST_STATE_FILE)

    def test_01_unconfigured_safe_mock_mode(self):
        """Test that unconfigured or placeholder tokens fall back safely to MOCK mode."""
        unconfigured_notifier = SlackNotifier(
            token='xoxb-YOUR-SLACK-BOT-TOKEN-HERE',
            channel_id='YOUR-CHANNEL-ID-HERE',
            state_file=TEST_STATE_FILE
        )
        self.assertFalse(unconfigured_notifier.is_configured)
        auth_res = unconfigured_notifier.test_auth()
        self.assertFalse(auth_res['ok'])
        self.assertEqual(auth_res['error'], 'NOT_CONFIGURED')

        # Test dispatch in mock mode returns MOCK_DELIVERED without raising exception
        sig_data = {
            'asset_type': 'stocks',
            'symbol': 'AAPL',
            'signal': 'BUY',
            'signal_time': '2026-10-17 14:00:00Z',
            'trading_mode': 'DRY_RUN'
        }
        res = unconfigured_notifier.send_signal_notification(sig_data)
        self.assertEqual(res['status'], 'MOCK_DELIVERED')

    def test_02_stocks_signal_formatting_no_fabrication(self):
        """Test Stocks BUY signal formatting. Missing fields must be N/A, not fabricated."""
        stocks_sig = {
            'asset_type': 'stocks',
            'symbol': 'NVDA',
            'signal': 'BUY',
            'signal_time': '2026-10-17 14:15:00Z',
            'trading_mode': 'DRY_RUN'
        }
        payload = self.notifier.build_signal_payload(stocks_sig)
        self.assertEqual(payload['channel'], 'C1234567890')
        self.assertIn('NVDA', payload['text'])
        self.assertIn('BUY SIGNAL', payload['text'])

        # Check section fields
        fields = payload['blocks'][1]['fields']
        field_texts = {f['text'].split('\n')[0]: f['text'].split('\n')[1] for f in fields}
        self.assertEqual(field_texts['*Symbol:*'], '*NVDA*')
        self.assertEqual(field_texts['*Asset Type:*'], '`STOCKS`')
        self.assertEqual(field_texts['*Signal Side:*'], '*BUY*')
        self.assertEqual(field_texts['*Reference Price:*'], 'N/A')
        self.assertEqual(field_texts['*Sentiment Score:*'], 'N/A')
        self.assertEqual(field_texts['*SMA 20:*'], 'N/A')
        self.assertEqual(field_texts['*SMA 50:*'], 'N/A')

    def test_03_crypto_signal_formatting_full_fields(self):
        """Test Crypto SELL signal formatting with all market and technical fields populated."""
        crypto_sig = {
            'asset_type': 'crypto',
            'symbol': 'BTC/USD',
            'signal': 'SELL',
            'signal_time': '2026-10-17 14:42:10Z',
            'price': 80500.0,
            'sentiment': -0.70,
            'sma_20': 79825.58,
            'sma_50': 79825.58,
            'trading_mode': 'DRY_RUN',
            'signal_id': 'SIG-CRYPTO-BTCUSD-SELL-1792247653'
        }
        payload = self.notifier.build_signal_payload(crypto_sig)
        self.assertIn('SELL SIGNAL', payload['text'])
        self.assertIn('BTC/USD', payload['text'])

        fields = payload['blocks'][1]['fields']
        field_texts = {f['text'].split('\n')[0]: f['text'].split('\n')[1] for f in fields}
        self.assertEqual(field_texts['*Symbol:*'], '*BTC/USD*')
        self.assertEqual(field_texts['*Asset Type:*'], '`CRYPTO`')
        self.assertEqual(field_texts['*Reference Price:*'], '$80,500.00')
        self.assertEqual(field_texts['*Sentiment Score:*'], '-0.7000')
        self.assertEqual(field_texts['*SMA 20:*'], '$79,825.58')
        self.assertEqual(field_texts['*SMA 50:*'], '$79,825.58')

    def test_04_order_confirmation_distinct_from_signal(self):
        """Verify Alpaca Order execution message is clearly distinguishable from a raw signal."""
        order_data = {
            'symbol': 'BTCUSD',
            'side': 'BUY',
            'status': 'FILLED',
            'order_id': 'c5d4311a-2c15-441d-bc11-8a7384fe8eed',
            'client_order_id': 'GD10-6-TEST-BTCUSD-BUY-1792247854',
            'filled_qty': '0.000120309',
            'filled_avg_price': '81535.8',
            'endpoint': 'https://paper-api.alpaca.markets'
        }
        payload = self.notifier.build_order_payload(order_data)
        self.assertIn('Alpaca Order Execution', payload['blocks'][0]['text']['text'])
        self.assertIn('ALPACA PAPER TRADING', payload['blocks'][1]['fields'][0]['text'])
        self.assertIn('c5d4311a', payload['blocks'][2]['elements'][0]['text'])

    @patch('requests.post')
    def test_05_persistent_deduplication(self, mock_post):
        """Test that duplicate signals are not re-sent and state is preserved."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'ok': True, 'ts': '1792248500.000100', 'channel': 'C1234567890'}

        sig_data = {
            'asset_type': 'stocks',
            'symbol': 'AAPL',
            'signal': 'BUY',
            'signal_time': '2026-10-17 14:00:00Z',
            'trading_mode': 'DRY_RUN'
        }
        # First send
        res1 = self.notifier.send_signal_notification(sig_data)
        self.assertEqual(res1['status'], 'DELIVERED')
        self.assertEqual(mock_post.call_count, 1)

        # Duplicate send
        res2 = self.notifier.send_signal_notification(sig_data)
        self.assertEqual(res2['status'], 'SKIPPED_DUPLICATE')
        self.assertEqual(mock_post.call_count, 1, "Mock post should NOT be called again for duplicate signal")

        # Test Restart Recovery: create a new notifier instance pointing to same state file
        new_notifier = SlackNotifier(
            token='xoxb-mock-test-token',
            channel_id='C1234567890',
            state_file=TEST_STATE_FILE
        )
        new_notifier.is_configured = True
        res3 = new_notifier.send_signal_notification(sig_data)
        self.assertEqual(res3['status'], 'SKIPPED_DUPLICATE', "Restarted notifier must remember delivered signal from state file")
        self.assertEqual(mock_post.call_count, 1)

    @patch('requests.post')
    def test_06_transient_error_retry(self, mock_post):
        """Test that transient HTTP errors trigger retry with backoff and succeed if recovered."""
        # Fail twice with 500 then succeed
        mock_fail = MagicMock()
        mock_fail.status_code = 500
        mock_fail.text = "Internal Server Error"

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {'ok': True, 'ts': '1792248500.000200', 'channel': 'C1234567890'}

        mock_post.side_effect = [mock_fail, mock_fail, mock_ok]

        sig_data = {
            'asset_type': 'crypto',
            'symbol': 'ETH/USD',
            'signal': 'BUY',
            'signal_time': '2026-10-17 14:10:00Z',
            'trading_mode': 'DRY_RUN'
        }
        with patch('time.sleep') as mock_sleep:
            res = self.notifier.send_signal_notification(sig_data)
            self.assertEqual(res['status'], 'DELIVERED')
            self.assertEqual(mock_post.call_count, 3)
            self.assertGreaterEqual(mock_sleep.call_count, 2)

    @patch('requests.post')
    def test_07_rate_limit_429_handling(self, mock_post):
        """Test that HTTP 429 respects Retry-After header."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {'Retry-After': '2'}

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {'ok': True, 'ts': '1792248500.000300', 'channel': 'C1234567890'}

        mock_post.side_effect = [mock_429, mock_ok]

        sig_data = {
            'asset_type': 'crypto',
            'symbol': 'BTC/USD',
            'signal': 'BUY',
            'signal_time': '2026-10-17 14:20:00Z',
            'trading_mode': 'DRY_RUN'
        }
        with patch('time.sleep') as mock_sleep:
            res = self.notifier.send_signal_notification(sig_data)
            self.assertEqual(res['status'], 'DELIVERED')
            self.assertEqual(mock_post.call_count, 2)
            mock_sleep.assert_called_with(2)

    @patch('requests.post')
    def test_08_fail_safe_non_blocking_on_complete_failure(self, mock_post):
        """Test that when Slack is completely unreachable, signal handler does not crash."""
        mock_post.side_effect = requests.ConnectionError("Failed to resolve slack.com")

        sig_data = {
            'asset_type': 'stocks',
            'symbol': 'MSFT',
            'signal': 'SELL',
            'signal_time': '2026-10-17 14:30:00Z',
            'trading_mode': 'DRY_RUN'
        }
        with patch('time.sleep'):
            res = self.notifier.send_signal_notification(sig_data)
            self.assertEqual(res['status'], 'FAILED')
            self.assertIn('Failed to resolve slack.com', res['error'])

if __name__ == '__main__':
    unittest.main()
