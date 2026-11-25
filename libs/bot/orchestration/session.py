"""
libs/bot/orchestration/session.py — Session Persistence & Store (GĐ34)
Manages atomic disk persistence and recovery of BotSession entities.
Storage directory: data/paper_bot/sessions/
"""

from typing import Dict, Any, List, Optional
import json
import os
from datetime import datetime, timezone

from libs.bot.domain import BotSession


class SessionStore:
    """
    Handles atomic persistence and retrieval of BotSession records.
    """

    def __init__(self, storage_dir: str = "data/paper_bot/sessions"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.log_path = os.path.join(self.storage_dir, "sessions_log.jsonl")

    def _get_path(self, session_id: str) -> str:
        return os.path.join(self.storage_dir, f"{session_id}.json")

    def save_session(self, session: BotSession) -> str:
        """
        Atomically saves BotSession to JSON file and appends to journal log.
        Returns the saved file path.
        """
        payload = {
            "session_id": session.session_id,
            "bot_session_id": session.bot_session_id,
            "bot_id": session.bot_id,
            "bot_name": session.bot_name,
            "strategy_name": session.strategy_name,
            "strategy_id": session.strategy_id,
            "strategy_version": session.strategy_version,
            "symbols": session.symbols,
            "timeframe": session.timeframe,
            "initial_cash": session.initial_cash,
            "risk_config_hash": session.risk_config_hash,
            "execution_config_hash": session.execution_config_hash,
            "data_consumer_group": session.data_consumer_group,
            "status": session.status,
            "lifecycle_state": session.lifecycle_state,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "paused_at": session.paused_at.isoformat() if session.paused_at else None,
            "stopped_at": session.stopped_at.isoformat() if session.stopped_at else None,
            "last_heartbeat_at": session.last_heartbeat_at.isoformat() if session.last_heartbeat_at else None,
            "last_processed_event_id": session.last_processed_event_id,
            "last_processed_bar_key": session.last_processed_bar_key,
            "checkpoint_id": session.checkpoint_id,
            "error_code": session.error_code,
            "error_message": session.error_message,
            "created_at": session.created_at.isoformat() if isinstance(session.created_at, datetime) else str(session.created_at),
            "updated_at": session.updated_at.isoformat() if isinstance(session.updated_at, datetime) else str(session.updated_at),
            "environment": session.environment,
            "trading_mode": session.trading_mode,
            "metadata": session.metadata,
        }

        file_path = self._get_path(session.bot_session_id)
        temp_path = f"{file_path}.tmp"

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(temp_path, file_path)

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

        return file_path

    def get_session(self, session_id: str) -> Optional[BotSession]:
        """Loads BotSession from disk by ID."""
        file_path = self._get_path(session_id)
        if not os.path.exists(file_path):
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            d = json.load(f)

        if d.get("environment") != "SIMULATION":
            raise ValueError(f"Security error: Session {session_id} is not tagged SIMULATION")

        started_at = datetime.fromisoformat(d["started_at"]) if d.get("started_at") else None
        paused_at = datetime.fromisoformat(d["paused_at"]) if d.get("paused_at") else None
        stopped_at = datetime.fromisoformat(d["stopped_at"]) if d.get("stopped_at") else None
        last_hb = datetime.fromisoformat(d["last_heartbeat_at"]) if d.get("last_heartbeat_at") else None

        return BotSession(
            session_id=d.get("session_id", session_id),
            bot_session_id=d.get("bot_session_id", session_id),
            bot_id=d.get("bot_id", "bot_v2_default"),
            bot_name=d.get("bot_name", "PaperBotV2"),
            strategy_name=d.get("strategy_name", "MA_CROSS"),
            strategy_id=d.get("strategy_id", "MA_CROSS_1M"),
            strategy_version=d.get("strategy_version", "1.0.0"),
            symbols=d.get("symbols", ["NVDA"]),
            timeframe=d.get("timeframe", "1m"),
            initial_cash=d.get("initial_cash", 100000.0),
            risk_config_hash=d.get("risk_config_hash", ""),
            execution_config_hash=d.get("execution_config_hash", ""),
            data_consumer_group=d.get("data_consumer_group", "paper-bot-v2-group"),
            status=d.get("status", "STOPPED"),
            lifecycle_state=d.get("lifecycle_state", "STOPPED"),
            started_at=started_at,
            paused_at=paused_at,
            stopped_at=stopped_at,
            last_heartbeat_at=last_hb,
            last_processed_event_id=d.get("last_processed_event_id", ""),
            last_processed_bar_key=d.get("last_processed_bar_key", ""),
            checkpoint_id=d.get("checkpoint_id", ""),
            error_code=d.get("error_code"),
            error_message=d.get("error_message"),
            environment=d.get("environment", "SIMULATION"),
            trading_mode=d.get("trading_mode", "DRY_RUN"),
            metadata=d.get("metadata", {}),
        )

    def list_all_sessions(self) -> List[BotSession]:
        """Lists all persisted bot sessions."""
        sessions = []
        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json"):
                sid = fname[:-5]
                s = self.get_session(sid)
                if s:
                    sessions.append(s)
        return sessions
