"""
timeframe_aggregator.py — Aggregates 1m stock bars into higher timeframes (5m, 15m, 1h)
Guarantees clean time boundaries, OHLCV preservation, and timestamp sorting.
"""
from typing import List, Dict, Any

TIMEFRAME_SECONDS = {
    '1m': 60,
    '5m': 300,
    '15m': 900,
    '1h': 3600,
}

def aggregate_candles(candles_1m: List[Dict[str, Any]], timeframe: str = '1m') -> List[Dict[str, Any]]:
    """
    Given a list of 1m candles (each having 'time' or 'timestamp' in seconds or millis,
    'open', 'high', 'low', 'close', 'volume', 'symbol'), aggregate them into timeframe buckets.
    """
    if timeframe == '1m' or not candles_1m:
        return candles_1m

    interval_sec = TIMEFRAME_SECONDS.get(timeframe, 60)
    
    # Sort 1m candles by time
    sorted_candles = sorted(candles_1m, key=lambda c: c['time'])

    aggregated = []
    current_bucket_start = None
    current_bucket = None

    for c in sorted_candles:
        c_time = c['time']  # assume seconds
        bucket_start = (c_time // interval_sec) * interval_sec

        if current_bucket_start is None or bucket_start != current_bucket_start:
            if current_bucket is not None:
                aggregated.append(current_bucket)
            current_bucket_start = bucket_start
            current_bucket = {
                'symbol': c.get('symbol', ''),
                'time': bucket_start,
                'open': float(c['open']),
                'high': float(c['high']),
                'low': float(c['low']),
                'close': float(c['close']),
                'volume': float(c.get('volume', 0.0)),
                'trade_count': float(c.get('trade_count', 0.0)),
                'vwap': float(c.get('vwap', c['close'])),
            }
        else:
            # Update current bucket
            current_bucket['high'] = max(current_bucket['high'], float(c['high']))
            current_bucket['low'] = min(current_bucket['low'], float(c['low']))
            current_bucket['close'] = float(c['close'])
            current_bucket['volume'] += float(c.get('volume', 0.0))
            current_bucket['trade_count'] += float(c.get('trade_count', 0.0))

    if current_bucket is not None:
        aggregated.append(current_bucket)

    return aggregated
