"""
libs/bot/indicators/sma.py — Simple Moving Average (SMA) Indicator (GĐ31)
Formula: SMA(n) = Sum(Close of last n bars) / n
Deterministic calculation with explicit warmup enforcement.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from libs.bot.domain import MarketDataEvent
from libs.bot.indicators.result import IndicatorResult


class SMAIndicator:
    """Simple Moving Average (SMA) calculator."""

    def __init__(self, period: int = 20, version: str = "1.0.0"):
        if period <= 0:
            raise ValueError(f"SMA period must be positive, got {period}")
        self.period = period
        self.version = version
        self.indicator_id = f"SMA_{period}"
        # price history per symbol: symbol -> List[float]
        self._history: Dict[str, List[float]] = {}

    def reset(self, symbol: Optional[str] = None) -> None:
        if symbol:
            self._history.pop(symbol, None)
        else:
            self._history.clear()

    def update(self, bar: MarketDataEvent) -> IndicatorResult:
        """Processes incoming finalized MarketDataEvent and computes SMA."""
        symbol = bar.symbol
        if symbol not in self._history:
            self._history[symbol] = []

        self._history[symbol].append(bar.close)
        prices = self._history[symbol]

        if len(prices) < self.period:
            return IndicatorResult(
                indicator_id=self.indicator_id,
                indicator_version=self.version,
                symbol=symbol,
                timeframe=bar.timeframe,
                event_time=bar.event_time,
                value=None,
                parameters={"period": self.period},
                warmup_complete=False,
                data_quality_status="WARMUP_INCOMPLETE",
                source_bar_revision=bar.bar_revision,
            )

        # Compute SMA on exact last 'period' bars
        sma_val = sum(prices[-self.period:]) / self.period
        return IndicatorResult(
            indicator_id=self.indicator_id,
            indicator_version=self.version,
            symbol=symbol,
            timeframe=bar.timeframe,
            event_time=bar.event_time,
            value=round(sma_val, 6),
            parameters={"period": self.period},
            warmup_complete=True,
            data_quality_status="VALID",
            source_bar_revision=bar.bar_revision,
        )
