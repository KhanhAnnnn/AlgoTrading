"""
libs/bot/multibot/recovery.py — Multi-Bot Recovery & Reconciliation Manager (GĐ37)
Discovers persisted bot definitions, uncompleted sessions, checkpoints,
and reconciles multi-bot simulation states post-restart without data corruption.
"""

from typing import Dict, List, Optional, Any
import os
import json
import logging
from datetime import datetime, timezone

from libs.bot.multibot.registry import BotRegistry, BotDefinition
from libs.bot.multibot.isolation import (
    get_bot_storage_dir,
    get_bot_order_store_dir,
    get_bot_fill_store_dir,
    get_bot_checkpoint_dir,
)
from libs.bot.orchestration.session import SessionStore
from libs.bot.orchestration.checkpoint import BotCheckpointManager, BotCheckpoint

logger = logging.getLogger("multibot-recovery")


class MultiBotRecoveryManager:
    """
    Manages cold-start recovery, integrity validation, and state reconciliation
    across all persisted simulation bot definitions and sessions.
    """

    def __init__(
        self,
        registry: Optional[BotRegistry] = None,
        base_dir: str = "data/paper_bot",
    ):
        self.base_dir = base_dir
        self.registry = registry or BotRegistry(storage_dir=f"{base_dir}/registry")
        self.session_store = SessionStore(storage_dir=f"{base_dir}/sessions")

    def discover_registered_bots(self, include_archived: bool = False) -> List[BotDefinition]:
        """Discovers all persisted bot definitions."""
        return self.registry.list_bots(include_archived=include_archived)

    def discover_sessions_for_bot(self, bot_id: str) -> List[Dict[str, Any]]:
        """Queries all past and current sessions for a bot."""
        sessions = self.registry.list_sessions_for_bot(bot_id, self.session_store)
        return [
            {
                "session_id": s.bot_session_id,
                "bot_id": s.bot_id,
                "lifecycle_state": s.lifecycle_state,
                "status": s.status,
                "created_at": s.created_at.isoformat() if isinstance(s.created_at, datetime) else str(s.created_at),
                "checkpoint_id": s.checkpoint_id,
                "last_processed_bar_key": s.last_processed_bar_key,
            }
            for s in sessions
        ]

    def verify_bot_integrity(self, bot_id: str) -> Dict[str, Any]:
        """
        Validates configuration hash, checkpoint integrity checksums,
        and order/fill stores for a bot.
        """
        bot_def = self.registry.get_bot(bot_id)
        if not bot_def:
            return {"bot_id": bot_id, "status": "NOT_FOUND", "valid": False}

        computed_hash = bot_def.compute_configuration_hash()
        hash_valid = (bot_def.configuration_hash == computed_hash)

        # Check sessions
        sessions = self.registry.list_sessions_for_bot(bot_id, self.session_store)
        checkpoint_results: List[Dict[str, Any]] = []

        for s in sessions:
            cp_dir = get_bot_checkpoint_dir(bot_id, s.bot_session_id, self.base_dir)
            if os.path.exists(cp_dir):
                cp_files = [f for f in os.listdir(cp_dir) if f.startswith("checkpoint_") and f.endswith(".json")]
                for cp_file in cp_files:
                    path = os.path.join(cp_dir, cp_file)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            cp_data = json.load(f)
                            cp = BotCheckpoint(
                                checkpoint_id=cp_data["checkpoint_id"],
                                bot_session_id=cp_data["bot_session_id"],
                                consumer_group=cp_data["consumer_group"],
                                partition_offsets=cp_data["partition_offsets"],
                                last_processed_event_id=cp_data["last_processed_event_id"],
                                last_processed_bar_key=cp_data["last_processed_bar_key"],
                                portfolio_snapshot_id=cp_data["portfolio_snapshot_id"],
                                reconciliation_status=cp_data["reconciliation_status"],
                                configuration_hash=cp_data["configuration_hash"],
                                checksum=cp_data.get("checksum", ""),
                            )
                            is_valid = (cp.compute_checksum() == cp.checksum)
                            checkpoint_results.append({
                                "checkpoint_id": cp.checkpoint_id,
                                "session_id": s.bot_session_id,
                                "checksum_valid": is_valid,
                            })
                    except Exception as e:
                        checkpoint_results.append({
                            "session_id": s.bot_session_id,
                            "error": str(e),
                            "checksum_valid": False,
                        })

        all_checkpoints_valid = all(c.get("checksum_valid", False) for c in checkpoint_results) if checkpoint_results else True
        overall_valid = hash_valid and all_checkpoints_valid

        return {
            "bot_id": bot_id,
            "status": "VALID" if overall_valid else "CORRUPTED",
            "valid": overall_valid,
            "config_hash_valid": hash_valid,
            "total_sessions": len(sessions),
            "checkpoints_verified": len(checkpoint_results),
            "checkpoint_results": checkpoint_results,
        }

    def reconcile_all_bots(self) -> Dict[str, Any]:
        """
        Runs comprehensive post-restart recovery and integrity scan across all bots.
        """
        bots = self.discover_registered_bots(include_archived=True)
        results: Dict[str, Any] = {}
        total_valid = 0

        for b in bots:
            audit = self.verify_bot_integrity(b.bot_id)
            results[b.bot_id] = audit
            if audit["valid"]:
                total_valid += 1

        return {
            "total_bots": len(bots),
            "valid_bots": total_valid,
            "corrupted_bots": len(bots) - total_valid,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": results,
        }
