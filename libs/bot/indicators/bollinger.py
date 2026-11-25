"""
libs/bot/indicators/bollinger.py — Bollinger Bands Indicator (GĐ31)
Baseline: Period 20, Multiplier 2.0
Output: Middle Band (SMA), Upper Band (Middle + Multiplier * StdDev),
        Lower Band (Middle - Multiplier * StdDev), Band Width ((Upper - Lower) / Middle)
Explicit Standard Deviation Policy: ddof=0 (population std dev) or ddof=1 (sample std dev).
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import math

from libs.bot.domain import MarketDataEvent
from libs.bot.indicators.result import IndicatorResult


class BollingerBandsIndicator:
    """Bollinger Bands indicator calculator."""

    def __init__(
        self,
        period: int = 20,
        multiplier: float = 2.0,
        ddof: int = 0,
        version: str = "1.0.0",
    ):
        if period <= 1:
            raise ValueError(f"Bollinger Bands period must be > 1, got {period}")
        if multiplier <= 0:
            raise ValueError(f"Multiplier must be positive, got {multiplier}")
        if ddof not in [0, 1]:
            raise ValueError(f"ddof must be 0 (population) or 1 (sample), got {ddof}")

        self.period = period
        self.multiplier = multiplier
        self.ddof = ddof
        self.version = version
        self.indicator_id = f"BB_{period}_{multiplier}_{ddof}"
        self._history: Dict[str, List[float]] = {}

    def reset(self, symbol: Optional[str] = None) -> None:
        if symbol:
            self._history.pop(symbol, None)
        else:
            self._history.clear()

    def update(self, bar: MarketDataEvent) -> IndicatorResult:
        symbol = bar.symbol
        if symbol not in self._history:
            self._history[symbol] = []

        self._history[symbol].append(bar.close)
        prices = self._history[symbol]

        params = {
            "period": self.period,
            "multiplier": self.multiplier,
            "ddof": self.ddof,
        }

        if len(prices) < self.period:
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

        window = prices[-self.period:]
        middle_band = sum(window) / self.period

        # Compute standard deviation
        variance = sum((x - middle_band) ** 2 for x in window) / (self.period - self.ddof)
        std_dev = math.sqrt(max(0.0, variance))

        upper_band = middle_band + (self.multiplier * std_dev)
        lower_band = middle_band - (self.multiplier * std_dev)
        band_width = ((upper_band - lower_band) / middle_band) if middle_band > 0 else 0.0

        return IndicatorResult(
            indicator_id=self.indicator_id,
            indicator_version=self.version,
            symbol=symbol,
            timeframe=bar.timeframe,
            event_time=bar.event_time,
            value={
                "middle_band": round(middle_band, 6),
                "upper_band": round(upper_band, 6),
                "lower_band": round(lower_band, 6),
                "band_width": round(band_width, 6),
                "std_dev": round(std_dev, 6),
            },
            parameters=params,
            warmup_complete=True,
            data_quality_status="VALID",
            source_bar_revision=bar.bar_revision,
        )
