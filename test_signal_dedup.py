"""
test_signal_dedup.py — Unit tests for Signal Handler deduplication and DRY_RUN logic
"""
import sys
import importlib.util

# Dynamically import signal-handler.py (has hyphen in filename)
spec = importlib.util.spec_from_file_location("signal_handler", "D:/AlgoTrading/signal-handler.py")
sh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sh)

sh.TRADING_MODE = 'DRY_RUN'

print("1. Checking initial state...")
sh._processed_signals.clear()
assert len(sh._processed_signals) == 0

msg = '{"symbol": "AAPL", "signal_time": "2026-10-17 10:00:00Z", "signal": "BUY"}'

print("2. Processing first message...")
sh.process_signal(msg)
assert len(sh._processed_signals) == 1, "Failed to register processed signal"

print("3. Processing duplicate message...")
sh.process_signal(msg)
assert len(sh._processed_signals) == 1, "Duplicate signal was not ignored!"

print("4. Processing different signal...")
msg2 = '{"symbol": "AAPL", "signal_time": "2026-10-17 10:05:00Z", "signal": "SELL"}'
sh.process_signal(msg2)
assert len(sh._processed_signals) == 2, "Second distinct signal was not registered!"

print("\nSUCCESS: All Signal Handler deduplication and validation tests PASSED!")
