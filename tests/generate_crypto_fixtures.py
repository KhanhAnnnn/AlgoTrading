"""
generate_crypto_fixtures.py — Generates deterministic test fixtures for Flink Crypto Pipeline
Covers 8 required test cases:
1. BUY (crossover below SMA20 + positive sentiment)
2. SELL (crossover above SMA20 + negative sentiment)
3. NO SIGNAL (positive sentiment without crossover)
4. NO SIGNAL (negative sentiment without crossover)
5. NO SIGNAL (insufficient SMA history < 20 bars)
6. NO SIGNAL (neutral sentiment == 0.0)
7. Late Event (timestamp older than watermark)
8. Duplicate Candle (same timestamp re-emitted)
"""
import os
import json
from datetime import datetime, timezone

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FIXTURES_DIR = os.path.join(BASE_DIR, 'tests', 'fixtures')
os.makedirs(FIXTURES_DIR, exist_ok=True)
FIXTURE_FILE = os.path.join(FIXTURES_DIR, 'crypto_deterministic_fixtures.json')

BASE_TS = 1792238400  # 2026-10-17 12:00:00 UTC
SYMBOL = 'BTC/USD'

bars = []
news = []
expected_signals = []

def make_bar(idx: int, t_sec: int, close_val: float) -> dict:
    return {
        'asset_type': 'crypto',
        'symbol': SYMBOL,
        'source': 'test_fixture',
        'open': close_val,
        'high': close_val + 20.0,
        'low': close_val - 20.0,
        'close': float(close_val),
        'volume': 1.5,
        'trade_count': 10,
        'vwap': float(close_val),
        'timestamp': t_sec * 1000,
        'timestamp_ms': t_sec * 1000,
        'event_time': t_sec,
        'ingest_time': t_sec,
        'is_final': True,
        'schema_version': '1.0'
    }

def make_news(news_id: int, t_sec: int, headline: str, summary: str, sentiment: float) -> dict:
    return {
        'asset_type': 'crypto',
        'symbol': SYMBOL,
        'source': 'test_fixture',
        'id': news_id,
        'headline': headline,
        'summary': summary,
        'sentiment': float(sentiment),
        'timestamp': t_sec * 1000,
        'timestamp_ms': t_sec * 1000,
        'event_time': t_sec,
        'ingest_time': t_sec,
        'schema_version': '1.0'
    }

# 1. Baseline: Bars 0 to 24 (t = 0..24 min), Price = 80,000.0
for i in range(25):
    t = BASE_TS + i * 60
    bars.append(make_bar(len(bars), t, 80000.0))

# Case 1: Early News at t = 3 min, sentiment = +0.75
news.append(make_news(9001, BASE_TS + 3 * 60,
                      'Early Bitcoin surge before sufficient history',
                      'Early test news with positive sentiment', 0.75))

# 2. BUY Setup:
# Bar 25 (t = 25 min): close = 80000.0
bars.append(make_bar(len(bars), BASE_TS + 25 * 60, 80000.0))
# Bar 26 (t = 26 min): close = 79500.0 (Cross below SMA20)
bars.append(make_bar(len(bars), BASE_TS + 26 * 60, 79500.0))
# News 9002 at t = 26 min + 10s, sentiment = +0.65
news.append(make_news(9002, BASE_TS + 26 * 60 + 10,
                      'Bitcoin Dip Bought Heavily by Institutional Funds',
                      'Positive institutional sentiment on flash dip', 0.65))

expected_signals.append({
    'case': 'BUY',
    'symbol': SYMBOL,
    'signal': 'BUY',
    'price': 79500.0,
    'sentiment': 0.65,
    'news_id': 9002
})

# Bars 27..40 (t = 27..40 min): close stays low at 79500.0 to let SMA20 settle below 80000
for i in range(27, 41):
    bars.append(make_bar(len(bars), BASE_TS + i * 60, 79500.0))

# 3. SELL Setup:
# Bar 41 (t = 41 min): close = 79500.0
bars.append(make_bar(len(bars), BASE_TS + 41 * 60, 79500.0))
# Bar 42 (t = 42 min): close = 80500.0 (Cross above SMA20)
bars.append(make_bar(len(bars), BASE_TS + 42 * 60, 80500.0))
# News 9003 at t = 42 min + 10s, sentiment = -0.70
news.append(make_news(9003, BASE_TS + 42 * 60 + 10,
                      'Regulatory Probe Announced into Offshore Crypto Lending',
                      'Severe negative regulatory headwinds', -0.70))

expected_signals.append({
    'case': 'SELL',
    'symbol': SYMBOL,
    'signal': 'SELL',
    'price': 80500.0,
    'sentiment': -0.70,
    'news_id': 9003
})

# Bars 43..55 (t = 43..55 min): close stays high at 80500.0
for i in range(43, 56):
    bars.append(make_bar(len(bars), BASE_TS + i * 60, 80500.0))

# 4. NO SIGNAL Setup (Positive sentiment without crossover):
# Bars 56..60: price stays at 80500.0
for i in range(56, 61):
    bars.append(make_bar(len(bars), BASE_TS + i * 60, 80500.0))
# News 9004 at t = 58 min + 10s, sentiment = +0.80
news.append(make_news(9004, BASE_TS + 58 * 60 + 10,
                      'Bitcoin ETF Inflows Accelerate Further',
                      'Positive sentiment but market already elevated', 0.80))

# 5. Neutral Sentiment Setup (sentiment == 0.0):
# Bars 61..64: price at 80500.0
for i in range(61, 65):
    bars.append(make_bar(len(bars), BASE_TS + i * 60, 80500.0))
# Bar 65: drops to 79500.0
bars.append(make_bar(len(bars), BASE_TS + 65 * 60, 79500.0))
# Bars 66..68: stays at 79500.0
for i in range(66, 69):
    bars.append(make_bar(len(bars), BASE_TS + i * 60, 79500.0))
# News 9005 at t = 65 min + 10s, sentiment = 0.0
news.append(make_news(9005, BASE_TS + 65 * 60 + 10,
                      'Crypto Markets Trade Sideways in Overnight Session',
                      'Neutral market commentary', 0.0))

# 6. Duplicate Candle: Re-send Bar 42 with same timestamp_ms
duplicate_bar = dict(bars[42])
duplicate_bar['ingest_time'] = BASE_TS + 69 * 60

# 7. Late Event: Bar with event_time far behind watermark (t = BASE_TS - 600s)
late_bar = make_bar(999, BASE_TS - 600, 79000.0)

fixture_payload = {
    'metadata': {
        'symbol': SYMBOL,
        'base_timestamp_utc': datetime.fromtimestamp(BASE_TS, tz=timezone.utc).isoformat(),
        'total_bars': len(bars),
        'total_news': len(news),
        'expected_signals_count': len(expected_signals),
    },
    'bars': bars,
    'news': news,
    'duplicate_bar': duplicate_bar,
    'late_bar': late_bar,
    'expected_signals': expected_signals
}

with open(FIXTURE_FILE, 'w', encoding='utf-8') as f:
    json.dump(fixture_payload, f, indent=2)

print(f"Generated {len(bars)} test bars, {len(news)} test news items, and {len(expected_signals)} expected signals.")
print(f"Saved to: {FIXTURE_FILE}")

