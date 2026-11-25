"""
libs/bot/multibot/registry.py — Bot Definition Registry & Session Association (GĐ37)
Provides persistent storage, lifecycle registration, hash validation, and session lookup
for multi-bot configurations without touching active live trading states.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import hashlib
import json
import os
import uuid
import logging

from libs.bot.domain import BotSession
from libs.bot.orchestration.session import SessionStore

logger = logging.getLogger("multibot-registry")


@dataclass
class BotDefinition:
    """
    Persistent configuration entity for a Paper Trading Bot.
    Separates persistent bot identity and strategy from ephemeral runtime sessions.
    """
    bot_id: str
    bot_name: str = ""
    strategy_id: str = "MA_CROSS_1M"
    strategy_version: str = "1.0.0"
    symbols: List[str] = field(default_factory=lambda: ["NVDA", "BTC/USD"])
    timeframe: str = "1m"
    initial_simulated_cash: float = 100000.0
    risk_config: Dict[str, Any] = field(default_factory=dict)
    execution_config: Dict[str, Any] = field(default_factory=dict)
    resource_policy: Optional[Dict[str, Any]] = None
    strategy_preset_id: Optional[str] = None
    strategy_config_version: Optional[str] = None
    pending_preset: Optional[Dict[str, Any]] = None
    configuration_hash: str = ""
    enabled: bool = True
    archived: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    environment: str = "SIMULATION"
    trading_mode: str = "DRY_RUN"

    def __post_init__(self):
        if not self.bot_name:
            self.bot_name = self.bot_id
        if not self.configuration_hash:
            self.configuration_hash = self.compute_configuration_hash()

    def compute_configuration_hash(self) -> str:
        """Deterministic SHA-256 fingerprint of bot definition parameters."""
        sorted_symbols = sorted(self.symbols)
        risk_str = json.dumps(self.risk_config, sort_keys=True)
        exec_str = json.dumps(self.execution_config, sort_keys=True)
        payload = (
            f"{self.bot_id}:{self.strategy_id}:{self.strategy_version}:"
            f"{','.join(sorted_symbols)}:{self.timeframe}:{self.initial_simulated_cash}:"
            f"{risk_str}:{exec_str}:{self.strategy_preset_id or ''}:{self.strategy_config_version or ''}:"
            f"{self.environment}:{self.trading_mode}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def bind_preset(self, preset_id: str, version: str = "1.0.0", config_hash: str = "") -> None:
        """Binds a strategy preset to this bot definition."""
        self.strategy_preset_id = preset_id
        self.strategy_config_version = version
        self.configuration_hash = self.compute_configuration_hash()
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes BotDefinition to dictionary."""
        return {
            "bot_id": self.bot_id,
            "bot_name": self.bot_name,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "symbols": list(self.symbols),
            "timeframe": self.timeframe,
            "initial_simulated_cash": float(self.initial_simulated_cash),
            "risk_config": self.risk_config,
            "execution_config": self.execution_config,
            "resource_policy": self.resource_policy,
            "strategy_preset_id": self.strategy_preset_id,
            "strategy_config_version": self.strategy_config_version,
            "pending_preset": self.pending_preset,
            "configuration_hash": self.configuration_hash or self.compute_configuration_hash(),
            "enabled": self.enabled,
            "archived": self.archived,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else str(self.updated_at),
            "environment": self.environment,
            "trading_mode": self.trading_mode,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BotDefinition":
        """Instantiates BotDefinition from serialized dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except Exception:
                created_at = datetime.now(timezone.utc)
        elif not isinstance(created_at, datetime):
            created_at = datetime.now(timezone.utc)

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at)
            except Exception:
                updated_at = datetime.now(timezone.utc)
        elif not isinstance(updated_at, datetime):
            updated_at = datetime.now(timezone.utc)

        return cls(
            bot_id=data["bot_id"],
            bot_name=data.get("bot_name", data["bot_id"]),
            strategy_id=data.get("strategy_id", "MA_CROSS_1M"),
            strategy_version=data.get("strategy_version", "1.0.0"),
            symbols=data.get("symbols", ["NVDA", "BTC/USD"]),
            timeframe=data.get("timeframe", "1m"),
            initial_simulated_cash=float(data.get("initial_simulated_cash", 100000.0)),
            risk_config=data.get("risk_config", {}),
            execution_config=data.get("execution_config", {}),
            resource_policy=data.get("resource_policy"),
            strategy_preset_id=data.get("strategy_preset_id"),
            strategy_config_version=data.get("strategy_config_version"),
            pending_preset=data.get("pending_preset"),
            configuration_hash=data.get("configuration_hash", ""),
            enabled=data.get("enabled", True),
            archived=data.get("archived", False),
            created_at=created_at,
            updated_at=updated_at,
            environment=data.get("environment", "SIMULATION"),
            trading_mode=data.get("trading_mode", "DRY_RUN"),
        )


class BotRegistry:
    """
    Manages persistent registry of BotDefinitions in data/paper_bot/registry/bots.json.
    Supports registration, querying, updating, archiving, and session association.
    """

    def __init__(self, storage_dir: str = "data/paper_bot/registry"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.registry_file = os.path.join(self.storage_dir, "bots.json")
        self._bots: Dict[str, BotDefinition] = {}
        self.load_from_disk()

    def load_from_disk(self) -> None:
        """Loads bot definitions from disk registry file."""
        if not os.path.exists(self.registry_file):
            return

        try:
            with open(self.registry_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    bots_data = data.get("bots", [])
                elif isinstance(data, list):
                    bots_data = data
                else:
                    bots_data = []

                for item in bots_data:
                    bot_def = BotDefinition.from_dict(item)
                    self._bots[bot_def.bot_id] = bot_def
            logger.info(f"Loaded {len(self._bots)} bot definitions from {self.registry_file}")
        except Exception as e:
            logger.error(f"Failed to load bot registry from {self.registry_file}: {e}")

    def save_to_disk(self) -> None:
        """Atomically persists bot definitions to disk using temporary file."""
        temp_file = f"{self.registry_file}.tmp"
        payload = {
            "version": "2.0.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "environment": "SIMULATION",
            "bots": [b.to_dict() for b in self._bots.values()],
        }
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(temp_file, self.registry_file)

    def register_bot(self, definition: BotDefinition) -> BotDefinition:
        """Registers a new bot definition. Fails if bot_id already exists."""
        if not definition.bot_id:
            raise ValueError("bot_id cannot be empty")
        if definition.bot_id in self._bots:
            raise ValueError(f"Bot with ID '{definition.bot_id}' is already registered")

        # Safety boundary assertions
        definition.environment = "SIMULATION"
        definition.trading_mode = "DRY_RUN"
        definition.configuration_hash = definition.compute_configuration_hash()
        definition.created_at = datetime.now(timezone.utc)
        definition.updated_at = datetime.now(timezone.utc)

        self._bots[definition.bot_id] = definition
        self.save_to_disk()
        logger.info(f"Registered bot '{definition.bot_id}' (strategy={definition.strategy_id})")
        return definition

    def get_bot(self, bot_id: str) -> Optional[BotDefinition]:
        """Retrieves a bot definition by bot_id."""
        return self._bots.get(bot_id)

    def list_bots(self, include_archived: bool = False) -> List[BotDefinition]:
        """Lists all registered bot definitions."""
        if include_archived:
            return list(self._bots.values())
        return [b for b in self._bots.values() if not b.archived]

    def update_bot(self, bot_id: str, updates: Dict[str, Any]) -> BotDefinition:
        """Updates mutable fields of a registered bot definition."""
        bot_def = self._bots.get(bot_id)
        if not bot_def:
            raise KeyError(f"Bot '{bot_id}' not found in registry")

        # Prohibit modifying safety boundaries
        updates.pop("environment", None)
        updates.pop("trading_mode", None)
        updates.pop("bot_id", None)

        if "bot_name" in updates:
            bot_def.bot_name = str(updates["bot_name"])
        if "symbols" in updates:
            bot_def.symbols = list(updates["symbols"])
        if "timeframe" in updates:
            bot_def.timeframe = str(updates["timeframe"])
        if "risk_config" in updates:
            bot_def.risk_config.update(updates["risk_config"])
        if "execution_config" in updates:
            bot_def.execution_config.update(updates["execution_config"])
        if "resource_policy" in updates:
            bot_def.resource_policy = updates["resource_policy"]
        if "enabled" in updates:
            bot_def.enabled = bool(updates["enabled"])

        bot_def.updated_at = datetime.now(timezone.utc)
        bot_def.configuration_hash = bot_def.compute_configuration_hash()

        self.save_to_disk()
        return bot_def

    def archive_bot(self, bot_id: str) -> bool:
        """
        Soft-archives a bot definition (sets archived=True, enabled=False).
        Does NOT delete historical sessions, orders, or fills.
        """
        bot_def = self._bots.get(bot_id)
        if not bot_def:
            raise KeyError(f"Bot '{bot_id}' not found in registry")

        bot_def.archived = True
        bot_def.enabled = False
        bot_def.updated_at = datetime.now(timezone.utc)
        self.save_to_disk()
        logger.info(f"Archived bot definition '{bot_id}' (historical data preserved)")
        return True

    def list_sessions_for_bot(
        self,
        bot_id: str,
        session_store: Optional[SessionStore] = None,
    ) -> List[BotSession]:
        """Queries all past and current sessions belonging to a specific bot_id."""
        if session_store is None:
            base = os.path.dirname(self.storage_dir) if self.storage_dir else "data/paper_bot"
            store = SessionStore(storage_dir=os.path.join(base, "sessions"))
        else:
            store = session_store
        all_sessions = store.list_all_sessions()
        bot_sessions = [s for s in all_sessions if s.bot_id == bot_id]
        bot_sessions.sort(key=lambda s: s.created_at, reverse=True)
        return bot_sessions
