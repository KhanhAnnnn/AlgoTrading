"""
libs/bot/strategies/ma_crossover.py — Moving Average Crossover Strategy (GĐ31)
Baseline: Fast SMA 20, Slow SMA 50 on finalized 1-minute bars.
Signal Conditions:
- Bullish Crossover: Previous Fast <= Previous Slow AND Current Fast > Current Slow -> BUY
- Bearish Crossover: Previous Fast >= Previous Slow AND Current Fast < Current Slow -> SELL
Deterministic, no future data leak, no signals on incomplete warmup.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid

from libs.bot.domain import MarketDataEvent, StrategySignal
from libs.bot.strategies.base import BaseStrategy
from libs.bot.indicators.sma import SMAIndicator


class MovingAverageCrossoverStrategy(BaseStrategy):
    """
    Moving Average Crossover Strategy.
    Computes Fast SMA and Slow SMA on finalized 1m bars.
    """

    def __init__(
        self,
        fast_period: int = 20,
        slow_period: int = 50,
        strategy_id: str = "MA_CROSS_1M",
        strategy_version: str = "1.0.0",
        require_final: bool = True,
        emit_hold: bool = False,
        # Backward compatibility aliases for GĐ29
        short_window: Optional[int] = None,
        long_window: Optional[int] = None,
        strategy_name: Optional[str] = None,
    ):
        actual_fast = short_window if short_window is not None else fast_period
        actual_slow = long_window if long_window is not None else slow_period
        name = strategy_name or strategy_id

        if actual_fast >= actual_slow:
            raise ValueError(f"fast_period ({actual_fast}) must be strictly less than slow_period ({actual_slow})")

        config = {
            "fast_period": actual_fast,
            "slow_period": actual_slow,
            "require_final": require_final,
            "emit_hold": emit_hold,
        }

        super().__init__(
            strategy_id=strategy_id,
            strategy_name=name,
            strategy_version=strategy_version,
            configuration=config,
            required_timeframe="1m",
            required_warmup_bars=actual_slow + 1,
        )

        self.fast_period = actual_fast
        self.slow_period = actual_slow
        self.require_final = require_final
        self.emit_hold = emit_hold

        self._fast_indicators: Dict[str, SMAIndicator] = {}
        self._slow_indicators: Dict[str, SMAIndicator] = {}
        # Tracking previous values for crossover comparison: symbol -> {"prev_fast": float, "prev_slow": float}
        self._prev_values: Dict[str, Dict[str, Optional[float]]] = {}

    @property
    def configuration_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "fast_period": {"type": "integer", "minimum": 1, "default": 20},
                "slow_period": {"type": "integer", "minimum": 2, "default": 50},
                "require_final": {"type": "boolean", "default": True},
            },
            "required": ["fast_period", "slow_period"],
        }

    @property
    def required_indicators(self) -> List[str]:
        return [f"SMA_{self.fast_period}", f"SMA_{self.slow_period}"]

    def reset_state(self, symbol: Optional[str] = None) -> None:
        if symbol:
            if symbol in self._fast_indicators:
                self._fast_indicators[symbol].reset()
            if symbol in self._slow_indicators:
                self._slow_indicators[symbol].reset()
            self._prev_values.pop(symbol, None)
        else:
            self._fast_indicators.clear()
            self._slow_indicators.clear()
            self._prev_values.clear()

    def generate_signals(self, market_data: MarketDataEvent) -> Optional[StrategySignal]:
        symbol = market_data.symbol

        # 1. Finality check
        if self.require_final and not market_data.is_final:
            if not self.emit_hold:
                return None
            return StrategySignal(
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                symbol=symbol,
                timeframe=market_data.timeframe,
                signal_type="NO_SIGNAL",
                signal_time=market_data.event_time,
                price=market_data.close,
                reason="Provisional bar ignored by final_only policy",
                reason_codes=["BAR_NOT_FINAL"],
                source_bar_key=market_data.bar_key,
                source_bar_revision=market_data.bar_revision,
                configuration_hash=self.get_configuration_hash(),
                environment="SIMULATION",
            )

        # 2. Input validation
        if not self.validate_input(market_data):
            if not self.emit_hold:
                return None
            return StrategySignal(
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                symbol=symbol,
                timeframe=market_data.timeframe,
                signal_type="NO_SIGNAL",
                signal_time=market_data.event_time,
                price=market_data.close,
                reason="Market data event failed strategy input validation",
                reason_codes=["DATA_QUALITY_REJECTED"],
                source_bar_key=market_data.bar_key,
                source_bar_revision=market_data.bar_revision,
                configuration_hash=self.get_configuration_hash(),
                environment="SIMULATION",
            )

        # 3. Indicators update
        if symbol not in self._fast_indicators:
            self._fast_indicators[symbol] = SMAIndicator(period=self.fast_period)
            self._slow_indicators[symbol] = SMAIndicator(period=self.slow_period)
            self._prev_values[symbol] = {"prev_fast": None, "prev_slow": None}

        fast_res = self._fast_indicators[symbol].update(market_data)
        slow_res = self._slow_indicators[symbol].update(market_data)

        # 4. Warmup check
        if not fast_res.warmup_complete or not slow_res.warmup_complete or fast_res.value is None or slow_res.value is None:
            if not self.emit_hold:
                return None
            return StrategySignal(
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                symbol=symbol,
                timeframe=market_data.timeframe,
                signal_type="NO_SIGNAL",
                signal_time=market_data.event_time,
                price=market_data.close,
                reason=f"Warmup incomplete (required: {self.required_warmup_bars} bars)",
                reason_codes=["INSUFFICIENT_WARMUP"],
                source_bar_key=market_data.bar_key,
                source_bar_revision=market_data.bar_revision,
                configuration_hash=self.get_configuration_hash(),
                environment="SIMULATION",
            )

        curr_fast = fast_res.value
        curr_slow = slow_res.value
        prev = self._prev_values[symbol]
        prev_fast = prev["prev_fast"]
        prev_slow = prev["prev_slow"]

        # If this is the very first bar after warmup completes, store previous values and hold
        if prev_fast is None or prev_slow is None:
            prev["prev_fast"] = curr_fast
            prev["prev_slow"] = curr_slow
            if not self.emit_hold:
                return None
            return StrategySignal(
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                symbol=symbol,
                timeframe=market_data.timeframe,
                signal_type="HOLD",
                signal_time=market_data.event_time,
                price=market_data.close,
                indicator_values={"fast_sma": curr_fast, "slow_sma": curr_slow},
                reason="Warmup complete; seeded baseline values for crossover detection",
                reason_codes=["NO_STRATEGY_CONDITION"],
                source_bar_key=market_data.bar_key,
                source_bar_revision=market_data.bar_revision,
                configuration_hash=self.get_configuration_hash(),
                environment="SIMULATION",
            )

        signal_type = "HOLD"
        reason = "No crossover detected"
        reason_codes = ["NO_STRATEGY_CONDITION"]

        # Bullish Golden Cross: prev_fast <= prev_slow and curr_fast > curr_slow
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            signal_type = "BUY"
            reason = f"Bullish Golden Cross: Fast SMA {curr_fast:.2f} crossed above Slow SMA {curr_slow:.2f}"
            reason_codes = ["BULLISH_CROSSOVER"]

        # Bearish Death Cross: prev_fast >= prev_slow and curr_fast < curr_slow
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            signal_type = "SELL"
            reason = f"Bearish Death Cross: Fast SMA {curr_fast:.2f} crossed below Slow SMA {curr_slow:.2f}"
            reason_codes = ["BEARISH_CROSSOVER"]

        # Update previous values for next step
        prev["prev_fast"] = curr_fast
        prev["prev_slow"] = curr_slow

        # Final signal creation
        if signal_type in ["HOLD", "NO_SIGNAL"] and not self.emit_hold:
            return None

        return StrategySignal(
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            symbol=symbol,
            timeframe=market_data.timeframe,
            signal_type=signal_type,
            signal_time=market_data.event_time,
            price=market_data.close,
            strength=1.0,
            indicator_values={
                "fast_sma": curr_fast,
                "slow_sma": curr_slow,
                "prev_fast_sma": prev_fast,
                "prev_slow_sma": prev_slow,
            },
            reason=reason,
            reason_codes=reason_codes,
            source_bar_key=market_data.bar_key,
            source_bar_revision=market_data.bar_revision,
            configuration_hash=self.get_configuration_hash(),
            environment="SIMULATION",
        )
