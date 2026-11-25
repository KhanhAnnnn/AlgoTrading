"""
libs/bot/indicators/rsi.py — Relative Strength Index (RSI) Indicator (GĐ31)
Supports:
1. 'SIMPLE_ROLLING' (v1.0): Rolling average of gains/losses (as in Anil Gaddam's reference PDF).
2. 'WILDER' (v1.0): Classic Wilder Exponential Smoothing (alpha = 1 / period).
Handles edge cases: zero gain, zero loss, flat price (both zero), and warmup boundaries.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from libs.bot.domain import MarketDataEvent
from libs.bot.indicators.result import IndicatorResult


class RSIIndicator:
    """Relative Strength Index (RSI) calculator."""

    def __init__(self, period: int = 14, method: str = "SIMPLE_ROLLING", version: str = "1.0.0"):
        if period <= 0:
            raise ValueError(f"RSI period must be positive, got {period}")
        method_clean = method.upper()
        if method_clean not in ["SIMPLE_ROLLING", "WILDER"]:
            raise ValueError(f"Unknown RSI method '{method}'. Supported: 'SIMPLE_ROLLING', 'WILDER'")

        self.period = period
        self.method = method_clean
        self.version = version
        self.indicator_id = f"RSI_{period}_{self.method}"
        # Tracking per symbol: symbol -> {"prices": List[float], "prev_avg_gain": Optional[float], "prev_avg_loss": Optional[float]}
        self._state: Dict[str, Dict[str, Any]] = {}

    def reset(self, symbol: Optional[str] = None) -> None:
        if symbol:
            self._state.pop(symbol, None)
        else:
            self._state.clear()

    def update(self, bar: MarketDataEvent) -> IndicatorResult:
        symbol = bar.symbol
        if symbol not in self._state:
            self._state[symbol] = {"prices": [], "prev_avg_gain": None, "prev_avg_loss": None}

        state = self._state[symbol]
        state["prices"].append(bar.close)
        prices = state["prices"]

        # Warmup requires at least period + 1 prices to compute 'period' differences
        if len(prices) < self.period + 1:
            return IndicatorResult(
                indicator_id=self.indicator_id,
                indicator_version=self.version,
                symbol=symbol,
                timeframe=bar.timeframe,
                event_time=bar.event_time,
                value=None,
                parameters={"period": self.period, "method": self.method},
                warmup_complete=False,
                data_quality_status="WARMUP_INCOMPLETE",
                source_bar_revision=bar.bar_revision,
            )

        if self.method == "SIMPLE_ROLLING":
            # Method 1: Reference PDF simple rolling average of gains and losses over last 'period' bars
            window_prices = prices[-(self.period + 1):]
            gains = []
            losses = []
            for i in range(1, len(window_prices)):
                chg = window_prices[i] - window_prices[i - 1]
                if chg > 0:
                    gains.append(chg)
                    losses.append(0.0)
                else:
                    gains.append(0.0)
                    losses.append(abs(chg))

            avg_gain = sum(gains) / self.period
            avg_loss = sum(losses) / self.period

        else:
            # Method 2: Wilder Smoothing
            if state["prev_avg_gain"] is None:
                # Initial seed: simple average of first 'period' changes
                init_gains = []
                init_losses = []
                for i in range(1, self.period + 1):
                    chg = prices[i] - prices[i - 1]
                    if chg > 0:
                        init_gains.append(chg)
                        init_losses.append(0.0)
                    else:
                        init_gains.append(0.0)
                        init_losses.append(abs(chg))
                avg_gain = sum(init_gains) / self.period
                avg_loss = sum(init_losses) / self.period

                # Recurse forward if prices has more than period + 1 bars
                for i in range(self.period + 1, len(prices)):
                    chg = prices[i] - prices[i - 1]
                    curr_gain = chg if chg > 0 else 0.0
                    curr_loss = abs(chg) if chg < 0 else 0.0
                    avg_gain = ((avg_gain * (self.period - 1)) + curr_gain) / self.period
                    avg_loss = ((avg_loss * (self.period - 1)) + curr_loss) / self.period
            else:
                chg = prices[-1] - prices[-2]
                curr_gain = chg if chg > 0 else 0.0
                curr_loss = abs(chg) if chg < 0 else 0.0
                avg_gain = ((state["prev_avg_gain"] * (self.period - 1)) + curr_gain) / self.period
                avg_loss = ((state["prev_avg_loss"] * (self.period - 1)) + curr_loss) / self.period

            state["prev_avg_gain"] = avg_gain
            state["prev_avg_loss"] = avg_loss

        # Calculate RSI with explicit edge case handling
        if avg_gain == 0.0 and avg_loss == 0.0:
            rsi_val = 50.0  # Flat price
        elif avg_loss == 0.0:
            rsi_val = 100.0  # All gains
        elif avg_gain == 0.0:
            rsi_val = 0.0  # All losses
        else:
            rs = avg_gain / avg_loss
            rsi_val = 100.0 - (100.0 / (1.0 + rs))

        return IndicatorResult(
            indicator_id=self.indicator_id,
            indicator_version=self.version,
            symbol=symbol,
            timeframe=bar.timeframe,
            event_time=bar.event_time,
            value=round(rsi_val, 6),
            parameters={"period": self.period, "method": self.method, "avg_gain": avg_gain, "avg_loss": avg_loss},
            warmup_complete=True,
            data_quality_status="VALID",
            source_bar_revision=bar.bar_revision,
        )
