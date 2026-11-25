"""
backtest/strategies.py — Algorithmic Strategy Implementations
Implements 5 strategy variants:
1. Strategy 1 (PDF Baseline): Inverted Dip-Buying Crossover with current SMA comparison
2. Strategy 2 (Corrected Baseline): Inverted Dip-Buying with mathematically lagged SMA
3. Strategy 3 (Trend-Following Momentum): Bullish Breakout above SMA20 + Sentiment > 0
4. Strategy 4 (Dual SMA Golden/Death Cross): SMA20 crossing SMA50 + Sentiment Confirmation
5. Strategy 5 (Decaying Sentiment State): Trend Crossover with 60-minute Half-Life Sentiment
"""
import math
import pandas as pd
import numpy as np
from typing import Dict, Any, Callable

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Pre-calculates SMA-20, SMA-50, and their lagged values."""
    d = df.copy()
    d['sma_20'] = d['close'].rolling(20, min_periods=20).mean()
    d['sma_50'] = d['close'].rolling(50, min_periods=50).mean()
    d['lag_close'] = d['close'].shift(1)
    d['lag_sma_20'] = d['sma_20'].shift(1)
    d['lag_sma_50'] = d['sma_50'].shift(1)
    
    if 'sentiment' not in d.columns:
        d['sentiment'] = 0.0
    return d

def make_strategy_1_pdf_baseline() -> Callable[[pd.DataFrame], pd.Series]:
    """Strategy 1: PDF Baseline (Mean-Reversion dip-buying, current SMA comparison)."""
    def generate_signals(df: pd.DataFrame) -> pd.Series:
        d = compute_indicators(df)
        signals = pd.Series(index=d.index, dtype='object')
        
        # BUY: sentiment > 0 AND close < sma_20 AND lag_close >= sma_20 (current sma)
        buy_cond = (d['sentiment'] > 0) & (d['close'] < d['sma_20']) & (d['lag_close'] >= d['sma_20'])
        # SELL: sentiment < 0 AND close > sma_20 AND lag_close <= sma_20 (current sma)
        sell_cond = (d['sentiment'] < 0) & (d['close'] > d['sma_20']) & (d['lag_close'] <= d['sma_20'])
        
        signals[buy_cond] = 'BUY'
        signals[sell_cond] = 'SELL'
        return signals
    return generate_signals

def make_strategy_2_corrected_baseline() -> Callable[[pd.DataFrame], pd.Series]:
    """Strategy 2: Corrected Baseline (Mean-Reversion dip-buying, strictly lagged SMA)."""
    def generate_signals(df: pd.DataFrame) -> pd.Series:
        d = compute_indicators(df)
        signals = pd.Series(index=d.index, dtype='object')
        
        # BUY: sentiment > 0 AND close < sma_20 AND lag_close >= lag_sma_20
        buy_cond = (d['sentiment'] > 0) & (d['close'] < d['sma_20']) & (d['lag_close'] >= d['lag_sma_20'])
        # SELL: sentiment < 0 AND close > sma_20 AND lag_close <= lag_sma_20
        sell_cond = (d['sentiment'] < 0) & (d['close'] > d['sma_20']) & (d['lag_close'] <= d['lag_sma_20'])
        
        signals[buy_cond] = 'BUY'
        signals[sell_cond] = 'SELL'
        return signals
    return generate_signals

def make_strategy_3_trend_momentum() -> Callable[[pd.DataFrame], pd.Series]:
    """Strategy 3: Trend-Following Momentum (Breakout above SMA20 + Sentiment > 0)."""
    def generate_signals(df: pd.DataFrame) -> pd.Series:
        d = compute_indicators(df)
        signals = pd.Series(index=d.index, dtype='object')
        
        # BUY: sentiment > 0 AND close > sma_20 AND lag_close <= lag_sma_20
        buy_cond = (d['sentiment'] > 0) & (d['close'] > d['sma_20']) & (d['lag_close'] <= d['lag_sma_20'])
        # SELL: sentiment < 0 AND close < sma_20 AND lag_close >= lag_sma_20
        sell_cond = (d['sentiment'] < 0) & (d['close'] < d['sma_20']) & (d['lag_close'] >= d['lag_sma_20'])
        
        signals[buy_cond] = 'BUY'
        signals[sell_cond] = 'SELL'
        return signals
    return generate_signals

def make_strategy_4_dual_sma() -> Callable[[pd.DataFrame], pd.Series]:
    """Strategy 4: Dual SMA Crossover (SMA20 crosses SMA50 + Sentiment Confirmation)."""
    def generate_signals(df: pd.DataFrame) -> pd.Series:
        d = compute_indicators(df)
        signals = pd.Series(index=d.index, dtype='object')
        
        # Golden Cross BUY: sma20 > sma50 AND lag_sma20 <= lag_sma50 AND sentiment > 0
        buy_cond = (d['sma_20'] > d['sma_50']) & (d['lag_sma_20'] <= d['lag_sma_50']) & (d['sentiment'] > 0)
        # Death Cross SELL: sma20 < sma50 AND lag_sma20 >= lag_sma50 AND sentiment < 0
        sell_cond = (d['sma_20'] < d['sma_50']) & (d['lag_sma_20'] >= d['lag_sma_50']) & (d['sentiment'] < 0)
        
        signals[buy_cond] = 'BUY'
        signals[sell_cond] = 'SELL'
        return signals
    return generate_signals

def make_strategy_5_decaying_sentiment(half_life_bars: int = 60) -> Callable[[pd.DataFrame], pd.Series]:
    """Strategy 5: Trend Momentum with Stateful Exponentially Decaying Sentiment."""
    def generate_signals(df: pd.DataFrame) -> pd.Series:
        d = compute_indicators(df)
        signals = pd.Series(index=d.index, dtype='object')
        
        # Apply exponential decay to sentiment state across bars
        alpha = 1.0 - math.exp(-math.log(2) / max(1, half_life_bars))
        decayed_sentiment = d['sentiment'].ewm(alpha=alpha, adjust=False).mean()
        
        # Trend breakout confirmed by decayed sentiment state
        buy_cond = (decayed_sentiment > 0.05) & (d['close'] > d['sma_20']) & (d['lag_close'] <= d['lag_sma_20'])
        sell_cond = (decayed_sentiment < -0.05) & (d['close'] < d['sma_20']) & (d['lag_close'] >= d['lag_sma_20'])
        
        signals[buy_cond] = 'BUY'
        signals[sell_cond] = 'SELL'
        return signals
    return generate_signals
