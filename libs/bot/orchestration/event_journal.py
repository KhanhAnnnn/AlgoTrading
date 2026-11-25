"""
libs/bot/orchestration/event_journal.py — Ingestion Event Journal & Deduplication Cache (GĐ34)
Maintains an append-only journal of all processed market data events per session.
Guarantees event deduplication and replay safety.
Storage directory: data/paper_bot/journal/
"""

from typing import Dict, Any, List, Set, Optional
import json
import os
from datetime import datetime, timezone


class BotEventJournal:
    """
    Append-only journal tracking processed market events for idempotency and crash recovery.
    """

    def __init__(self, session_id: str, storage_dir: str = "data/paper_bot/journal"):
        self.session_id = session_id
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.journal_path = os.path.join(self.storage_dir, f"journal_{session_id}.jsonl")
        self.log_file = self.journal_path

        self._seen_bar_keys: Set[str] = set()
        self._seen_event_ids: Set[str] = set()
        self._load_journal()

    def _load_journal(self) -> None:
        """Loads existing entries into memory set for deduplication."""
        if not os.path.exists(self.journal_path):
            return
        with open(self.journal_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if "bar_key" in record and record["bar_key"]:
                            self._seen_bar_keys.add(record["bar_key"])
                        if "event_id" in record and record["event_id"]:
                            self._seen_event_ids.add(record["event_id"])
                    except json.JSONDecodeError:
                        continue

    def is_processed(self, bar_key: str, event_id: Optional[str] = None) -> bool:
        """Checks if a bar or event has already been committed to the journal."""
        if bar_key in self._seen_bar_keys:
            return True
        if event_id and event_id in self._seen_event_ids:
            return True
        return False

    def record_processed_event(
        self,
        bar_key: str,
        event_id: str,
        status: str = "PROCESSED",
        signals_generated: int = 0,
        fills_generated: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Appends a processed event record to the journal."""
        entry = {
            "session_id": self.session_id,
            "bar_key": bar_key,
            "event_id": event_id,
            "status": status,
            "signals_generated": signals_generated,
            "fills_generated": fills_generated,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": "SIMULATION",
        }

        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        self._seen_bar_keys.add(bar_key)
        self._seen_event_ids.add(event_id)

    def get_processed_count(self) -> int:
        """Returns total count of unique bars processed."""
        return len(self._seen_bar_keys)
