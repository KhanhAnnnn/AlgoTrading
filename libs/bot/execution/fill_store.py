"""
libs/bot/execution/fill_store.py — Persistent Simulated Fill Store (GĐ33)
Manages atomic disk persistence and audit replay of SimulatedFills.
Storage location: data/paper_bot/fills/
"""

from typing import Dict, Any, List, Optional
import json
import os
from datetime import datetime, timezone

from libs.bot.domain import SimulatedFill


class FillStore:
    """
    Handles atomic persistence and retrieval of SimulatedFills.
    """

    def __init__(self, storage_dir: str = "data/paper_bot/fills"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.log_path = os.path.join(self.storage_dir, "fills_log.jsonl")
        self._seen_fill_ids: set[str] = set()
        self._load_existing_indices()

    def _load_existing_indices(self) -> None:
        """Loads fill IDs from log."""
        if not os.path.exists(self.log_path):
            return
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if "fill_id" in record:
                            self._seen_fill_ids.add(record["fill_id"])
                    except json.JSONDecodeError:
                        continue

    def save_fill(self, fill: SimulatedFill) -> str:
        """
        Atomically saves fill to disk and appends to audit log.
        Returns the saved JSON file path.
        """
        payload = {
            "fill_id": fill.simulated_fill_id,
            "order_id": fill.simulated_order_id,
            "intent_id": fill.intent_id,
            "bot_session_id": fill.bot_session_id,
            "symbol": fill.symbol,
            "side": fill.side,
            "fill_price": fill.fill_price,
            "fill_qty": fill.fill_qty,
            "fill_time": fill.fill_time.isoformat() if isinstance(fill.fill_time, datetime) else str(fill.fill_time),
            "fee": fill.fee,
            "fee_currency": fill.fee_currency,
            "slippage": fill.slippage,
            "source_bar_key": fill.source_bar_key,
            "execution_bar_key": fill.execution_bar_key,
            "assumptions": fill.assumptions,
            "metadata": fill.metadata,
            "environment": fill.environment,
        }

        file_path = os.path.join(self.storage_dir, f"{fill.simulated_fill_id}.json")
        temp_path = f"{file_path}.tmp"

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(temp_path, file_path)

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

        self._seen_fill_ids.add(fill.simulated_fill_id)
        return file_path

    def get_fill(self, fill_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves raw fill data from disk."""
        file_path = os.path.join(self.storage_dir, f"{fill_id}.json")
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_all_fills(self) -> List[Dict[str, Any]]:
        """Loads all saved fills from disk for recovery and audit reconciliation."""
        fills = []
        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.storage_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    fills.append(json.load(f))
        return fills
