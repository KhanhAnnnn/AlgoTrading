"""
libs/bot/signal_store.py — Strategy & Signal Persistence (GĐ31)
Persists strategy signals, indicator snapshots, and configurations
under 'data/paper_bot/strategies/' in thread-safe JSON/JSONL format.
"""

from typing import Dict, Any, List, Optional
import os
import json
from datetime import datetime, timezone

from libs.bot.domain import StrategySignal
from libs.bot.indicators.result import IndicatorResult


class SignalStore:
    """
    Persistence layer for strategy signals and evaluations.
    Maintains isolated files under data/paper_bot/strategies/.
    """

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            curr_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(curr_dir, "..", ".."))
            self.base_dir = os.path.join(project_root, "data", "paper_bot", "strategies")
        else:
            self.base_dir = base_dir

        self.signals_dir = os.path.join(self.base_dir, "signals")
        self.indicators_dir = os.path.join(self.base_dir, "indicators")
        self.configs_dir = os.path.join(self.base_dir, "configs")
        self.evaluations_dir = os.path.join(self.base_dir, "evaluations")

        for d in [self.signals_dir, self.indicators_dir, self.configs_dir, self.evaluations_dir]:
            os.makedirs(d, exist_ok=True)

        self.signals_log_file = os.path.join(self.signals_dir, "strategy_signals.jsonl")

    @staticmethod
    def _serialize_signal(sig: StrategySignal) -> Dict[str, Any]:
        return {
            "signal_id": sig.signal_id,
            "bot_session_id": sig.bot_session_id,
            "strategy_id": sig.strategy_id,
            "strategy_version": sig.strategy_version,
            "symbol": sig.symbol,
            "timeframe": sig.timeframe,
            "signal_type": sig.signal_type,
            "signal_time": sig.signal_time.isoformat() if isinstance(sig.signal_time, datetime) else str(sig.signal_time),
            "price": sig.price,
            "strength": sig.strength,
            "indicator_values": sig.indicator_values,
            "reason": sig.reason,
            "reason_codes": sig.reason_codes,
            "source_bar_key": sig.source_bar_key,
            "source_bar_revision": sig.source_bar_revision,
            "configuration_hash": sig.configuration_hash,
            "trace_id": sig.trace_id,
            "metadata": sig.metadata,
            "environment": sig.environment,
        }

    def save_signal(self, sig: StrategySignal) -> None:
        """Appends signal record to strategy_signals.jsonl."""
        payload = self._serialize_signal(sig)
        with open(self.signals_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

    def save_indicator_snapshot(self, result: IndicatorResult) -> None:
        """Appends indicator snapshot for audit and verification."""
        file_path = os.path.join(self.indicators_dir, f"indicators_{result.symbol.replace('/', '_')}.jsonl")
        payload = {
            "indicator_id": result.indicator_id,
            "indicator_version": result.indicator_version,
            "symbol": result.symbol,
            "timeframe": result.timeframe,
            "event_time": result.event_time.isoformat() if isinstance(result.event_time, datetime) else str(result.event_time),
            "value": result.value,
            "parameters": result.parameters,
            "warmup_complete": result.warmup_complete,
            "data_quality_status": result.data_quality_status,
            "source_bar_revision": result.source_bar_revision,
        }
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

    def save_evaluation_audit(self, entry: Dict[str, Any]) -> None:
        """Appends general evaluation audit record."""
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        file_path = os.path.join(self.evaluations_dir, "evaluations_audit.jsonl")
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def load_signals(self, strategy_id: Optional[str] = None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Loads logged signals with optional filters."""
        if not os.path.exists(self.signals_log_file):
            return []

        results = []
        with open(self.signals_log_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if strategy_id and data.get("strategy_id") != strategy_id:
                        continue
                    if symbol and data.get("symbol") != symbol:
                        continue
                    results.append(data)
                except Exception:
                    continue
        return results
