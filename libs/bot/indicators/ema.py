"""
libs/bot/indicators/ema.py — Exponential Moving Average (EMA) Indicator (GĐ31)
Smoothing factor: alpha = 2 / (period + 1)
Initialization: SMA of first 'period' bars.
Recurrence: EMA_t = Close_t * alpha + EMA_{t-1} * (1 - alpha)
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from libs.bot.domain import MarketDataEvent
from libs.bot.indicators.result import IndicatorResult


class EMAIndicator:
    """Exponential Moving Average (EMA) calculator."""

    def __init__(self, period: int = 12, version: str = "1.0.0"):
        if period <= 0:
            raise ValueError(f"EMA period must be positive, got {period}")
        self.period = period
        self.version = version
        self.indicator_id = f"EMA_{period}"
        self.alpha = 2.0 / (period + 1.0)
        # Tracking per symbol: symbol -> {"history": List[float], "current_ema": Optional[float]}
        self._state: Dict[str, Dict[str, Any]] = {}

    def reset(self, symbol: Optional[str] = None) -> None:
        if symbol:
            self._state.pop(symbol, None)
        else:
            self._state.clear()

    def update(self, bar: MarketDataEvent) -> IndicatorResult:
        symbol = bar.symbol
        if symbol not in self._state:
            self._state[symbol] = {"history": [], "current_ema": None}

        state = self._state[symbol]
        state["history"].append(bar.close)
        prices = state["history"]

        # Warmup check
        if len(prices) < self.period:
            return IndicatorResult(
                indicator_id=self.indicator_id,
                indicator_version=self.version,
                symbol=symbol,
                timeframe=bar.timeframe,
                event_time=bar.event_time,
                value=None,
                parameters={"period": self.period, "alpha": self.alpha},
                warmup_complete=False,
                data_quality_status="WARMUP_INCOMPLETE",
                source_bar_revision=bar.bar_revision,
            )

        # Initialization at exact period: SMA of first 'period' bars
        if state["current_ema"] is None:
            initial_sma = sum(prices[:self.period]) / self.period
            # Advance EMA from initial_sma through any subsequent points up to now
            current_ema = initial_sma
            for p in prices[self.period:]:
                current_ema = (p * self.alpha) + (current_ema * (1.0 - self.alpha))
            state["current_ema"] = current_ema
        else:
            # Recurrence step
            state["current_ema"] = (bar.close * self.alpha) + (state["current_ema"] * (1.0 - self.alpha))

        return IndicatorResult(
            indicator_id=self.indicator_id,
            indicator_version=self.version,
            symbol=symbol,
            timeframe=bar.timeframe,
            event_time=bar.event_time,
            value=round(state["current_ema"], 6),
            parameters={"period": self.period, "alpha": self.alpha},
            warmup_complete=True,
            data_quality_status="VALID",
            source_bar_revision=bar.bar_revision,
        )
