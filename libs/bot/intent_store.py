"""
libs/bot/intent_store.py — Simulation Order Intent Store (GĐ32)
Manages storage, retrieval, and idempotency checks for SimulationOrderIntents.
Persists intents strictly in data/paper_bot/intents/ ready for GĐ33 consumption.
"""

from typing import Dict, Any, List, Optional
import json
import os
from datetime import datetime, timezone

from libs.bot.domain import SimulationOrderIntent


class IntentStore:
    """
    Persists SimulationOrderIntent objects to disk and prevents duplicate submissions.
    """

    def __init__(self, storage_dir: str = "data/paper_bot/intents"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.log_path = os.path.join(self.storage_dir, "intents_log.jsonl")
        self._seen_idempotency_keys: set[str] = set()
        self._load_idempotency_keys()

    def _load_idempotency_keys(self) -> None:
        """Indexes all previously recorded idempotency keys from the log file."""
        if not os.path.exists(self.log_path):
            return
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if "idempotency_key" in record:
                            self._seen_idempotency_keys.add(record["idempotency_key"])
                    except json.JSONDecodeError:
                        continue

    def save_intent(self, intent: SimulationOrderIntent) -> tuple[bool, str]:
        """
        Saves intent atomically. Returns (is_new, file_path).
        If idempotency_key is already recorded, returns (False, existing_path).
        """
        if intent.idempotency_key in self._seen_idempotency_keys:
            file_path = os.path.join(self.storage_dir, f"{intent.intent_id}.json")
            return False, file_path

        payload = {
            "intent_id": intent.intent_id,
            "decision_id": intent.decision_id,
            "signal_id": intent.signal_id,
            "bot_session_id": intent.bot_session_id,
            "portfolio_id": intent.portfolio_id,
            "symbol": intent.symbol,
            "side": intent.side,
            "order_type": intent.order_type,
            "proposed_quantity": intent.proposed_quantity,
            "proposed_notional": intent.proposed_notional,
            "reference_price": intent.reference_price,
            "risk_configuration_version": intent.risk_configuration_version,
            "idempotency_key": intent.idempotency_key,
            "created_at": intent.created_at.isoformat() if isinstance(intent.created_at, datetime) else str(intent.created_at),
            "environment": intent.environment,
        }

        # 1. Save individual intent JSON
        file_path = os.path.join(self.storage_dir, f"{intent.intent_id}.json")
        temp_path = f"{file_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(temp_path, file_path)

        # 2. Append to JSONL log
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

        self._seen_idempotency_keys.add(intent.idempotency_key)
        return True, file_path

    def get_intent(self, intent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves an intent from disk by ID."""
        file_path = os.path.join(self.storage_dir, f"{intent_id}.json")
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
