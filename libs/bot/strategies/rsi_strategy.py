"""
libs/bot/strategies/rsi_strategy.py — Relative Strength Index Strategy (GĐ31)
Baseline: Period 14, Lower Threshold 30 (Oversold), Upper Threshold 70 (Overbought).
Distinguishes:
1. Region Entry (Threshold Crossed): Triggers BUY (oversold) or SELL (overbought).
2. Staying in Region: Suppresses duplicate/repetitive signals while price lingers in zone.
3. Region Exit: Tracks recovery to neutral state.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid

from libs.bot.domain import MarketDataEvent, StrategySignal
from libs.bot.strategies.base import BaseStrategy
from libs.bot.indicators.rsi import RSIIndicator


class RSIStrategy(BaseStrategy):
    """
    RSI Mean Reversion Strategy with Region Entry/Exit transition tracking.
    """

    def __init__(
        self,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        strategy_id: str = "RSI_1M",
        strategy_version: str = "1.0.0",
        method: str = "SIMPLE_ROLLING",
        require_final: bool = True,
        emit_hold: bool = False,
        strategy_name: Optional[str] = None,
    ):
        if oversold >= overbought:
            raise ValueError(f"oversold ({oversold}) must be strictly less than overbought ({overbought})")

        name = strategy_name or strategy_id
        config = {
            "period": period,
            "oversold": oversold,
            "overbought": overbought,
            "method": method,
            "require_final": require_final,
            "emit_hold": emit_hold,
        }

        super().__init__(
            strategy_id=strategy_id,
            strategy_name=name,
            strategy_version=strategy_version,
            configuration=config,
            required_timeframe="1m",
            required_warmup_bars=period + 1,
        )

        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.method = method
        self.require_final = require_final
        self.emit_hold = emit_hold

        self._indicators: Dict[str, RSIIndicator] = {}
        # Tracking last region state per symbol: "NEUTRAL", "OVERSOLD", "OVERBOUGHT"
        self._last_zone: Dict[str, str] = {}

    @property
    def configuration_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "period": {"type": "integer", "minimum": 2, "default": 14},
                "oversold": {"type": "number", "minimum": 0, "maximum": 50, "default": 30.0},
                "overbought": {"type": "number", "minimum": 50, "maximum": 100, "default": 70.0},
                "method": {"type": "string", "enum": ["SIMPLE_ROLLING", "WILDER"], "default": "SIMPLE_ROLLING"},
                "require_final": {"type": "boolean", "default": True},
            },
            "required": ["period", "oversold", "overbought"],
        }

    @property
    def required_indicators(self) -> List[str]:
        return [f"RSI_{self.period}_{self.method}"]

    def reset_state(self, symbol: Optional[str] = None) -> None:
        if symbol:
            if symbol in self._indicators:
                self._indicators[symbol].reset()
            self._last_zone.pop(symbol, None)
        else:
            self._indicators.clear()
            self._last_zone.clear()

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
        if symbol not in self._indicators:
            self._indicators[symbol] = RSIIndicator(period=self.period, method=self.method)
            self._last_zone[symbol] = "NEUTRAL"

        rsi_res = self._indicators[symbol].update(market_data)

        # 4. Warmup check
        if not rsi_res.warmup_complete or rsi_res.value is None:
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

        rsi = rsi_res.value
        last_zone = self._last_zone.get(symbol, "NEUTRAL")

        # Determine current zone
        if rsi < self.oversold:
            current_zone = "OVERSOLD"
        elif rsi > self.overbought:
            current_zone = "OVERBOUGHT"
        else:
            current_zone = "NEUTRAL"

        signal_type = "HOLD"
        reason = f"RSI {rsi:.2f} in {current_zone} state"
        reason_codes = ["NO_STRATEGY_CONDITION"]

        # Event: Entry into Oversold
        if current_zone == "OVERSOLD" and last_zone != "OVERSOLD":
            signal_type = "BUY"
            reason = f"RSI entered Oversold region ({rsi:.2f} < {self.oversold})"
            reason_codes = ["RSI_OVERSOLD_ENTRY"]

        # Event: Entry into Overbought
        elif current_zone == "OVERBOUGHT" and last_zone != "OVERBOUGHT":
            signal_type = "SELL"
            reason = f"RSI entered Overbought region ({rsi:.2f} > {self.overbought})"
            reason_codes = ["RSI_OVERBOUGHT_ENTRY"]

        # Lingering in Oversold or Overbought: suppress repeated signals
        elif current_zone in ["OVERSOLD", "OVERBOUGHT"] and current_zone == last_zone:
            signal_type = "HOLD"
            reason = f"RSI persisting in {current_zone} ({rsi:.2f}); repeated signal suppressed"
            reason_codes = ["RSI_IN_ZONE_NO_REPEAT"]

        # Event: Exit back to neutral
        elif current_zone == "NEUTRAL" and last_zone != "NEUTRAL":
            signal_type = "HOLD"
            reason = f"RSI exited {last_zone} region back to neutral ({rsi:.2f})"
            reason_codes = ["RSI_REGION_EXIT"]

        self._last_zone[symbol] = current_zone

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
            indicator_values={"rsi": rsi, "zone": current_zone, "last_zone": last_zone},
            reason=reason,
            reason_codes=reason_codes,
            source_bar_key=market_data.bar_key,
            source_bar_revision=market_data.bar_revision,
            configuration_hash=self.get_configuration_hash(),
            environment="SIMULATION",
        )
