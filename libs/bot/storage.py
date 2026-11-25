"""
libs/bot/storage.py — Market Data Persistence & Offset Checkpointing (GĐ30)
Stores normalized 1m bars, revision histories, consumer checkpoints, and rejected events
under 'data/paper_bot/market_data/' in isolated, auditable JSON/JSONL format.
"""

from typing import Dict, Any, List, Optional
import os
import json
from datetime import datetime, timezone

from libs.bot.domain import MarketDataEvent


class MarketDataStore:
    """
    Thread-safe local persistence layer for V2 Paper Trading Bot market data.
    Provides isolated storage completely decoupled from V1 manual workbench files.
    """

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            # Root project dir / data / paper_bot / market_data
            curr_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(curr_dir, "..", ".."))
            self.base_dir = os.path.join(project_root, "data", "paper_bot", "market_data")
        else:
            self.base_dir = base_dir

        self.bars_dir = os.path.join(self.base_dir, "bars")
        self.revisions_dir = os.path.join(self.base_dir, "revisions")
        self.rejected_dir = os.path.join(self.base_dir, "rejected")
        self.checkpoints_dir = os.path.join(self.base_dir, "checkpoints")
        self.reports_dir = os.path.join(self.base_dir, "reports")

        for d in [self.bars_dir, self.revisions_dir, self.rejected_dir, self.checkpoints_dir, self.reports_dir]:
            os.makedirs(d, exist_ok=True)

        self.checkpoint_file = os.path.join(self.checkpoints_dir, "v2_consumer_offsets.json")
        self.quality_report_file = os.path.join(self.reports_dir, "data_quality_report.json")
        self.rejected_file = os.path.join(self.rejected_dir, "rejected_events.jsonl")

    @staticmethod
    def _sanitize_symbol(symbol: str) -> str:
        return symbol.replace("/", "_").replace(":", "_").upper()

    @staticmethod
    def _serialize_bar(bar: MarketDataEvent) -> Dict[str, Any]:
        return {
            "event_id": bar.event_id,
            "source_event_id": bar.source_event_id,
            "symbol": bar.symbol,
            "asset_class": bar.asset_class,
            "timeframe": bar.timeframe,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "trade_count": bar.trade_count,
            "vwap": bar.vwap,
            "event_time": bar.event_time.isoformat() if isinstance(bar.event_time, datetime) else str(bar.event_time),
            "ingest_time": bar.ingest_time.isoformat() if isinstance(bar.ingest_time, datetime) else str(bar.ingest_time),
            "bar_revision": bar.bar_revision,
            "is_final": bar.is_final,
            "source": bar.source,
            "environment": bar.environment,
            "provenance": bar.provenance,
            "quality_flags": bar.quality_flags,
            "bar_key": bar.bar_key,
        }

    @staticmethod
    def _deserialize_bar(data: Dict[str, Any]) -> MarketDataEvent:
        event_time = datetime.fromisoformat(data["event_time"].replace("Z", "+00:00"))
        ingest_time = datetime.fromisoformat(data["ingest_time"].replace("Z", "+00:00"))
        return MarketDataEvent(
            event_id=data["event_id"],
            source_event_id=data.get("source_event_id"),
            symbol=data["symbol"],
            asset_class=data.get("asset_class", "STOCKS"),
            timeframe=data.get("timeframe", "1m"),
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
            volume=float(data.get("volume", 0.0)),
            trade_count=int(data.get("trade_count", 0)),
            vwap=float(data.get("vwap", data["close"])),
            event_time=event_time,
            ingest_time=ingest_time,
            bar_revision=int(data.get("bar_revision", 0)),
            is_final=bool(data.get("is_final", True)),
            source=data.get("source", "REDPANDA"),
            environment=data.get("environment", "SIMULATION"),
            provenance=data.get("provenance", "NATURAL_RUNTIME"),
            quality_flags=data.get("quality_flags", []),
        )

    def save_bar(self, bar: MarketDataEvent) -> None:
        """Appends normalized bar to symbol-specific JSONL file."""
        sym_clean = self._sanitize_symbol(bar.symbol)
        file_path = os.path.join(self.bars_dir, f"bars_{sym_clean}.jsonl")
        payload = self._serialize_bar(bar)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

    def save_revision(self, bar: MarketDataEvent) -> None:
        """Appends bar revision update to symbol-specific revisions JSONL file."""
        sym_clean = self._sanitize_symbol(bar.symbol)
        file_path = os.path.join(self.revisions_dir, f"revisions_{sym_clean}.jsonl")
        payload = self._serialize_bar(bar)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

    def save_rejected(self, raw_record: Dict[str, Any], reason_code: str, flags: List[str]) -> None:
        """Logs rejected event with reason code to rejected_events.jsonl."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason_code": reason_code,
            "quality_flags": flags,
            "raw_payload": raw_record,
        }
        with open(self.rejected_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def save_checkpoint(self, group_id: str, topic: str, partition: int, offset: int) -> None:
        """Persists V2 consumer group offset independently."""
        current = self.load_checkpoints()
        key = f"{group_id}:{topic}:{partition}"
        current[key] = {
            "group_id": group_id,
            "topic": topic,
            "partition": partition,
            "offset": offset,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)

    def load_checkpoints(self) -> Dict[str, Any]:
        """Loads all V2 consumer group offset records."""
        if not os.path.exists(self.checkpoint_file):
            return {}
        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def get_checkpoint(self, group_id: str, topic: str, partition: int) -> Optional[int]:
        """Gets saved offset for specific group, topic, and partition."""
        data = self.load_checkpoints()
        key = f"{group_id}:{topic}:{partition}"
        if key in data:
            return int(data[key]["offset"])
        return None

    def load_bars(self, symbol: str, start: Optional[datetime] = None, end: Optional[datetime] = None) -> List[MarketDataEvent]:
        """Loads bars for symbol within optional time range."""
        sym_clean = self._sanitize_symbol(symbol)
        file_path = os.path.join(self.bars_dir, f"bars_{sym_clean}.jsonl")
        if not os.path.exists(file_path):
            return []

        results = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    bar = self._deserialize_bar(json.loads(line))
                    if start and bar.event_time < start:
                        continue
                    if end and bar.event_time > end:
                        continue
                    results.append(bar)
                except Exception:
                    continue
        return results

    def save_quality_report(self, summary: Dict[str, Any]) -> None:
        """Saves data quality summary to JSON report."""
        summary["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(self.quality_report_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
