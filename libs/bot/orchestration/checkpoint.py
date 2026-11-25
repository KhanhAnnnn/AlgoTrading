"""
libs/bot/orchestration/checkpoint.py — Checkpoint Manager & Integrity Hashing (GĐ34)
Manages persistent session checkpoints with SHA-256 integrity checksums.
Storage directory: data/paper_bot/checkpoints/
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
import hashlib
import json
import os
from datetime import datetime, timezone


@dataclass
class BotCheckpoint:
    """Represents a persistent checkpoint state of an active bot session."""
    checkpoint_id: str
    bot_session_id: str
    consumer_group: str
    partition_offsets: Dict[str, int]
    last_processed_event_id: str
    last_processed_bar_key: str
    portfolio_snapshot_id: str
    reconciliation_status: str
    configuration_hash: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    checksum: str = ""
    environment: str = "SIMULATION"

    def compute_checksum(self) -> str:
        """Computes deterministic SHA-256 integrity hash."""
        payload = (
            f"{self.checkpoint_id}:{self.bot_session_id}:{self.consumer_group}:"
            f"{self.last_processed_bar_key}:{self.portfolio_snapshot_id}:"
            f"{self.configuration_hash}:{self.reconciliation_status}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BotCheckpointManager:
    """
    Saves and restores atomic bot checkpoints with checksum verification.
    """

    def __init__(self, storage_dir: str = "data/paper_bot/checkpoints"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_path(self, session_id: str) -> str:
        return os.path.join(self.storage_dir, f"checkpoint_{session_id}.json")

    def save_checkpoint(
        self,
        bot_session_id: str,
        consumer_group: str,
        partition_offsets: Dict[str, int],
        last_processed_event_id: str,
        last_processed_bar_key: str,
        portfolio_snapshot_id: str,
        reconciliation_status: str,
        configuration_hash: str,
    ) -> BotCheckpoint:
        """
        Creates and atomically persists a checkpoint to disk.
        """
        import uuid
        cp_id = f"cp_{uuid.uuid4().hex[:12]}"

        checkpoint = BotCheckpoint(
            checkpoint_id=cp_id,
            bot_session_id=bot_session_id,
            consumer_group=consumer_group,
            partition_offsets=partition_offsets,
            last_processed_event_id=last_processed_event_id,
            last_processed_bar_key=last_processed_bar_key,
            portfolio_snapshot_id=portfolio_snapshot_id,
            reconciliation_status=reconciliation_status,
            configuration_hash=configuration_hash,
            timestamp=datetime.now(timezone.utc),
            environment="SIMULATION",
        )
        checkpoint.checksum = checkpoint.compute_checksum()

        file_path = self._get_path(bot_session_id)
        temp_path = f"{file_path}.tmp"

        payload = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "bot_session_id": checkpoint.bot_session_id,
            "consumer_group": checkpoint.consumer_group,
            "partition_offsets": checkpoint.partition_offsets,
            "last_processed_event_id": checkpoint.last_processed_event_id,
            "last_processed_bar_key": checkpoint.last_processed_bar_key,
            "portfolio_snapshot_id": checkpoint.portfolio_snapshot_id,
            "reconciliation_status": checkpoint.reconciliation_status,
            "configuration_hash": checkpoint.configuration_hash,
            "timestamp": checkpoint.timestamp.isoformat(),
            "checksum": checkpoint.checksum,
            "environment": checkpoint.environment,
        }

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(temp_path, file_path)

        return checkpoint

    def load_checkpoint(self, bot_session_id: str) -> Optional[BotCheckpoint]:
        """Loads and verifies a persisted checkpoint from disk."""
        file_path = self._get_path(bot_session_id)
        if not os.path.exists(file_path):
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            d = json.load(f)

        checkpoint = BotCheckpoint(
            checkpoint_id=d["checkpoint_id"],
            bot_session_id=d["bot_session_id"],
            consumer_group=d["consumer_group"],
            partition_offsets=d.get("partition_offsets", {}),
            last_processed_event_id=d.get("last_processed_event_id", ""),
            last_processed_bar_key=d.get("last_processed_bar_key", ""),
            portfolio_snapshot_id=d.get("portfolio_snapshot_id", ""),
            reconciliation_status=d.get("reconciliation_status", "BALANCED"),
            configuration_hash=d.get("configuration_hash", ""),
            timestamp=datetime.fromisoformat(d["timestamp"]),
            checksum=d.get("checksum", ""),
            environment=d.get("environment", "SIMULATION"),
        )

        expected_checksum = checkpoint.compute_checksum()
        if checkpoint.checksum != expected_checksum:
            raise ValueError(
                f"Checkpoint integrity violation for session {bot_session_id}: checksum mismatch!"
            )

        return checkpoint
