"""
libs/bot/indicators/macd.py — Moving Average Convergence Divergence (MACD) Indicator (GĐ31)
Baseline: Fast EMA 12, Slow EMA 26, Signal EMA 9
Output: MACD line, Signal line, Histogram (MACD - Signal)
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from libs.bot.domain import MarketDataEvent
from libs.bot.indicators.result import IndicatorResult
from libs.bot.indicators.ema import EMAIndicator


class MACDIndicator:
    """MACD Indicator calculator."""

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        version: str = "1.0.0",
    ):
        if fast_period >= slow_period:
            raise ValueError(f"fast_period ({fast_period}) must be strictly less than slow_period ({slow_period})")
        if signal_period <= 0:
            raise ValueError(f"signal_period must be positive, got {signal_period}")

        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.version = version
        self.indicator_id = f"MACD_{fast_period}_{slow_period}_{signal_period}"

        self._fast_ema = EMAIndicator(period=fast_period, version=version)
        self._slow_ema = EMAIndicator(period=slow_period, version=version)
        self._signal_ema = EMAIndicator(period=signal_period, version=version)

        # Tracking macd values per symbol for signal line computation
        self._macd_history: Dict[str, List[float]] = {}

    def reset(self, symbol: Optional[str] = None) -> None:
        self._fast_ema.reset(symbol)
        self._slow_ema.reset(symbol)
        self._signal_ema.reset(symbol)
        if symbol:
            self._macd_history.pop(symbol, None)
        else:
            self._macd_history.clear()

    def update(self, bar: MarketDataEvent) -> IndicatorResult:
        symbol = bar.symbol
        if symbol not in self._macd_history:
            self._macd_history[symbol] = []

        fast_res = self._fast_ema.update(bar)
        slow_res = self._slow_ema.update(bar)

        params = {
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "signal_period": self.signal_period,
        }

        # Warmup requires slow EMA to be complete
        if not slow_res.warmup_complete or slow_res.value is None or fast_res.value is None:
            return IndicatorResult(
                indicator_id=self.indicator_id,
                indicator_version=self.version,
                symbol=symbol,
                timeframe=bar.timeframe,
                event_time=bar.event_time,
                value=None,
                parameters=params,
                warmup_complete=False,
                data_quality_status="WARMUP_INCOMPLETE",
                source_bar_revision=bar.bar_revision,
            )

        # MACD Line = Fast EMA - Slow EMA
        macd_line = fast_res.value - slow_res.value
        self._macd_history[symbol].append(macd_line)

        # Feed macd_line into synthetic bar for signal EMA
        synthetic_bar = MarketDataEvent(
            symbol=symbol,
            timeframe=bar.timeframe,
            close=macd_line,
            event_time=bar.event_time,
            bar_revision=bar.bar_revision,
            is_final=bar.is_final,
        )
        signal_res = self._signal_ema.update(synthetic_bar)

        if not signal_res.warmup_complete or signal_res.value is None:
            return IndicatorResult(
                indicator_id=self.indicator_id,
                indicator_version=self.version,
                symbol=symbol,
                timeframe=bar.timeframe,
                event_time=bar.event_time,
                value=None,
                parameters=params,
                warmup_complete=False,
                data_quality_status="SIGNAL_WARMUP_INCOMPLETE",
                source_bar_revision=bar.bar_revision,
            )

        signal_line = signal_res.value
        histogram = round(macd_line - signal_line, 6)

        return IndicatorResult(
            indicator_id=self.indicator_id,
            indicator_version=self.version,
            symbol=symbol,
            timeframe=bar.timeframe,
            event_time=bar.event_time,
            value={
                "macd_line": round(macd_line, 6),
                "signal_line": round(signal_line, 6),
                "histogram": histogram,
            },
            parameters=params,
            warmup_complete=True,
            data_quality_status="VALID",
            source_bar_revision=bar.bar_revision,
        )
