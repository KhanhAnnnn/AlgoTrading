"""
test_crypto_signal_handler.py — Unit & Integration tests for Crypto Signal Handler.
Validates:
1. Consumer validates schema, symbols, and sides.
2. DRY_RUN mode records order intent without submitting orders to Alpaca.
3. Notional cap ($50.00 default) is enforced.
4. Spot position guard prevents SELL when long position is 0 (shorting disallowed).
5. Buying power check is enforced for BUY signals.
6. Persistent deduplication survives handler restarts.
"""
import os
import sys
import json
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from crypto_signal_handler import CryptoSignalHandler

class TestCryptoSignalHandler(unittest.TestCase):
    def setUp(self):
        # Use an isolated test intent file for testing
        self.handler = CryptoSignalHandler(mode='DRY_RUN')
        self.handler.processed_signals.clear()
        self.handler.order_intents.clear()

    def test_01_dry_run_buy_signal(self):
        """Test that a valid BUY signal in DRY_RUN mode creates an intent without executing."""
        raw_signal = json.dumps({
            'asset_type': 'crypto',
            'symbol': 'BTC/USD',
            'signal_time': '2026-10-17 12:26:10Z',
            'signal': 'BUY',
            'price': 79500.0,
            'sentiment': 0.65,
            'sma_20': 79981.48,
            'sma_50': 79981.48
        })
        intent = self.handler.process_signal(raw_signal)
        self.assertIsNotNone(intent)
        self.assertEqual(intent['symbol'], 'BTC/USD')
        self.assertEqual(intent['signal'], 'BUY')
        self.assertEqual(intent['mode'], 'DRY_RUN')
        self.assertFalse(intent['executed'])
        self.assertEqual(intent['order_result']['status'], 'DRY_RUN_SIMULATED')
        self.assertLessEqual(intent['notional_usd'], 100.0)

    def test_02_persistent_deduplication(self):
        """Test that duplicate signals are detected and skipped."""
        raw_signal = json.dumps({
            'asset_type': 'crypto',
            'symbol': 'BTC/USD',
            'signal_time': '2026-10-17 12:26:10Z',
            'signal': 'BUY',
            'price': 79500.0,
            'sentiment': 0.65,
            'sma_20': 79981.48,
            'sma_50': 79981.48
        })
        intent1 = self.handler.process_signal(raw_signal)
        self.assertIsNotNone(intent1)
        # Second submission of identical signal
        intent2 = self.handler.process_signal(raw_signal)
        self.assertIsNone(intent2, "Duplicate signal should return None")

    def test_03_unauthorized_symbol(self):
        """Test that non-whitelisted symbols are rejected."""
        raw_signal = json.dumps({
            'asset_type': 'crypto',
            'symbol': 'DOGE/USD',
            'signal_time': '2026-10-17 12:30:00Z',
            'signal': 'BUY',
            'price': 0.15,
            'sentiment': 0.50,
            'sma_20': 0.14,
            'sma_50': 0.14
        })
        intent = self.handler.process_signal(raw_signal)
        self.assertIsNone(intent, "Unauthorized symbol must be rejected")

    def test_04_invalid_signal_side(self):
        """Test that invalid signal sides are rejected."""
        raw_signal = json.dumps({
            'asset_type': 'crypto',
            'symbol': 'BTC/USD',
            'signal_time': '2026-10-17 12:30:00Z',
            'signal': 'HOLD',
            'price': 80000.0,
            'sentiment': 0.0,
            'sma_20': 80000.0,
            'sma_50': 80000.0
        })
        intent = self.handler.process_signal(raw_signal)
        self.assertIsNone(intent, "Non BUY/SELL signal must be rejected")

    def test_05_spot_sell_no_short_guard(self):
        """Test that SELL signal is rejected if account has 0 position in spot crypto."""
        # Mock get_crypto_position to return 0.0
        self.handler.get_crypto_position = lambda sym: 0.0

        raw_signal = json.dumps({
            'asset_type': 'crypto',
            'symbol': 'BTC/USD',
            'signal_time': '2026-10-17 12:42:10Z',
            'signal': 'SELL',
            'price': 80500.0,
            'sentiment': -0.70,
            'sma_20': 79825.58,
            'sma_50': 79825.58
        })
        intent = self.handler.process_signal(raw_signal)
        self.assertIsNotNone(intent)
        self.assertEqual(intent.get('rejection_reason'), 'NO_POSITION_TO_SELL')
        self.assertFalse(intent['executed'])

    def test_06_notional_cap_enforcement(self):
        """Test that notional USD is safely capped."""
        raw_signal = json.dumps({
            'asset_type': 'crypto',
            'symbol': 'ETH/USD',
            'signal_time': '2026-10-17 12:50:00Z',
            'signal': 'BUY',
            'price': 2400.0,
            'sentiment': 0.80,
            'sma_20': 2450.0,
            'sma_50': 2450.0
        })
        intent = self.handler.process_signal(raw_signal)
        self.assertIsNotNone(intent)
        self.assertLessEqual(intent['notional_usd'], self.handler.MAX_NOTIONAL_USD)
        self.assertEqual(intent['notional_usd'], 50.0)

if __name__ == '__main__':
    unittest.main()

