"""
sma_calculator.py — Independent Simple Moving Average (SMA-20 & SMA-50) Calculator
Calculates rolling averages on Close prices and validates sufficient candle counts.
"""
from typing import List, Dict, Any, Tuple

def calculate_smas(candles: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Given a list of candles sorted by time asc:
    Returns (sma_20_series, sma_50_series) formatted for Lightweight Charts:
    [{'time': int_sec, 'value': float}]
    Only outputs points when sufficient historical candles exist (>= 20 for SMA20, >= 50 for SMA50).
    """
    if not candles:
        return [], []

    sma_20_series = []
    sma_50_series = []

    closes = [float(c['close']) for c in candles]
    times = [c['time'] for c in candles]

    # Rolling sum for SMA-20
    running_sum_20 = 0.0
    for i, c_close in enumerate(closes):
        running_sum_20 += c_close
        if i >= 20:
            running_sum_20 -= closes[i - 20]
        if i >= 19:
            avg_20 = round(running_sum_20 / 20.0, 4)
            sma_20_series.append({
                'time': times[i],
                'value': avg_20
            })

    # Rolling sum for SMA-50
    running_sum_50 = 0.0
    for i, c_close in enumerate(closes):
        running_sum_50 += c_close
        if i >= 50:
            running_sum_50 -= closes[i - 50]
        if i >= 49:
            avg_50 = round(running_sum_50 / 50.0, 4)
            sma_50_series.append({
                'time': times[i],
                'value': avg_50
            })

    return sma_20_series, sma_50_series


def get_latest_smas(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Returns the latest SMA-20 and SMA-50 scalar values with sufficiency flags."""
    sma20_series, sma50_series = calculate_smas(candles)
    return {
        'total_candles': len(candles),
        'sma_20': sma20_series[-1]['value'] if sma20_series else None,
        'sma_20_valid': len(candles) >= 20,
        'sma_50': sma50_series[-1]['value'] if sma50_series else None,
        'sma_50_valid': len(candles) >= 50,
    }
