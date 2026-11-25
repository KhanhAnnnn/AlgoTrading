"""
libs/bot/strategies/v1_adapter.py — V1 Flink Strategy 1 Read-Only Adapter (GĐ31)
Bridges V1 Flink SQL signals (trading-signals / crypto-signals) into standard StrategySignal entities.
Read-Only mode: preserves original source and provenance without mutating Flink jobs.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid

from libs.bot.domain import MarketDataEvent, StrategySignal
from libs.bot.strategies.base import BaseStrategy


class V1StrategyAdapter(BaseStrategy):
    """
    Read-Only Adapter for Apache Flink SQL Strategy 1 output.
    """

    def __init__(
        self,
        strategy_id: str = "V1_FLINK_ADAPTER",
        strategy_name: str = "V1_FLINK_STRATEGY_1",
        strategy_version: str = "1.0.0",
    ):
        super().__init__(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            configuration={"source": "APACHE_FLINK_SQL", "mode": "READ_ONLY"},
            required_timeframe="1m",
            required_warmup_bars=50,
        )

    @property
    def configuration_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "default": "APACHE_FLINK_SQL"},
                "mode": {"type": "string", "default": "READ_ONLY"},
            },
        }

    @property
    def required_indicators(self) -> List[str]:
        return ["FLINK_SMA_20", "FLINK_SMA_50"]

    def reset_state(self, symbol: Optional[str] = None) -> None:
        pass

    def generate_signals(self, market_data: MarketDataEvent) -> StrategySignal:
        """Passive adapter: direct bar evaluation generates NO_SIGNAL."""
        return StrategySignal(
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            symbol=market_data.symbol,
            timeframe=market_data.timeframe,
            signal_type="NO_SIGNAL",
            signal_time=market_data.event_time,
            price=market_data.close,
            reason="V1StrategyAdapter operates via Flink stream translation",
            reason_codes=["NO_STRATEGY_CONDITION"],
            source_bar_key=market_data.bar_key,
            source_bar_revision=market_data.bar_revision,
            configuration_hash=self.get_configuration_hash(),
            environment="SIMULATION",
        )

    def translate_flink_signal(self, payload: Dict[str, Any]) -> StrategySignal:
        """Translates a raw Flink SQL signal JSON into a standardized StrategySignal."""
        signal_type = str(payload.get("signal_type", "HOLD")).upper()
        if signal_type not in ["BUY", "SELL", "HOLD"]:
            signal_type = "HOLD"

        price = float(payload.get("price", payload.get("close", 0.0)))
        symbol = str(payload.get("symbol", "UNKNOWN"))
        reason = str(payload.get("reason", payload.get("strategy_name", "Flink Strategy 1 Trigger")))
        raw_ts = payload.get("timestamp_ms") or payload.get("timestamp")

        if raw_ts:
            signal_time = datetime.fromtimestamp(int(raw_ts) / 1000.0, tz=timezone.utc)
        else:
            signal_time = datetime.now(timezone.utc)

        return StrategySignal(
            signal_id=f"sig_flink_{uuid.uuid4().hex[:10]}",
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            symbol=symbol,
            timeframe="1m",
            signal_type=signal_type,
            signal_time=signal_time,
            price=price,
            strength=float(payload.get("strength", 1.0)),
            reason=reason,
            reason_codes=["FLINK_TRIGGER"],
            source_bar_key=f"{symbol}:1m:{signal_time.isoformat()}",
            configuration_hash=self.get_configuration_hash(),
            metadata={"raw_payload": payload, "provenance": "FLINK_SQL_SINK"},
            environment="SIMULATION",
        )
