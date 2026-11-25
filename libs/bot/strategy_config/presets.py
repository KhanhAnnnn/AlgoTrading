"""
libs/bot/strategy_config/presets.py — Immutable Strategy Presets & Store (GĐ38)
Provides persistent, versioned, immutable presets with deterministic configuration hashing.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import json
import os
import uuid
import logging

from libs.bot.strategy_config.versioning import compute_configuration_hash, canonical_serialize

logger = logging.getLogger("strategy-presets")


class PresetImmutableError(Exception):
    """Raised when an attempt is made to overwrite or modify an immutable or locked preset."""
    pass


class PresetNotFoundError(Exception):
    """Raised when a preset cannot be found in the store."""
    pass


@dataclass
class StrategyPreset:
    """
    Immutable Strategy Preset entity.
    Once locked or referenced by backtest runs/live bots, it cannot be modified in place.
    """
    preset_id: str
    preset_name: str
    strategy_id: str
    strategy_version: str = "1.0.0"
    parameters: Dict[str, Any] = field(default_factory=dict)
    risk_config_reference: Optional[str] = None
    execution_config_reference: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    configuration_hash: str = ""
    schema_version: str = "1.0"
    environment: str = "SIMULATION"
    is_immutable: bool = True
    locked_by_run: Optional[str] = None

    def __post_init__(self):
        if not self.configuration_hash:
            self.configuration_hash = self.compute_hash()

    def compute_hash(self) -> str:
        """Calculates deterministic configuration hash over immutable preset fields."""
        data = {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "parameters": self.parameters,
            "risk_config_reference": self.risk_config_reference,
            "execution_config_reference": self.execution_config_reference,
            "schema_version": self.schema_version,
            "environment": self.environment,
        }
        return compute_configuration_hash(data)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes preset to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyPreset":
        return cls(**data)


class PresetStore:
    """
    Filesystem storage for strategy presets in data/paper_bot/presets/.
    Strictly enforces immutability.
    """

    def __init__(self, storage_dir: str = "data/paper_bot/presets"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self._in_memory_presets: Dict[str, StrategyPreset] = {}
        self._load_all()

    def _preset_path(self, preset_id: str) -> str:
        safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in preset_id)
        return os.path.join(self.storage_dir, f"{safe_id}.json")

    def _load_all(self):
        if not os.path.exists(self.storage_dir):
            return
        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.storage_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        preset = StrategyPreset.from_dict(data)
                        self._in_memory_presets[preset.preset_id] = preset
                except Exception as e:
                    logger.warning(f"Failed to load preset from {fpath}: {e}")

    def save(self, preset: StrategyPreset, allow_overwrite: bool = False) -> None:
        """
        Saves a preset. Raises PresetImmutableError if the preset already exists
        and is immutable or locked.
        """
        existing = self._in_memory_presets.get(preset.preset_id)
        if existing and not allow_overwrite:
            if existing.is_immutable or existing.locked_by_run:
                raise PresetImmutableError(
                    f"Preset '{preset.preset_id}' is immutable/locked and cannot be modified in place. "
                    f"Create a new preset version or clone it instead."
                )

        # Recompute hash to guarantee consistency
        preset.configuration_hash = preset.compute_hash()
        self._in_memory_presets[preset.preset_id] = preset

        fpath = self._preset_path(preset.preset_id)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(preset.to_dict(), f, indent=2, sort_keys=True)
        logger.info(f"Saved preset '{preset.preset_id}' (hash={preset.configuration_hash[:8]})")

    def get(self, preset_id: str) -> StrategyPreset:
        """Retrieves a preset by ID."""
        preset = self._in_memory_presets.get(preset_id)
        if not preset:
            raise PresetNotFoundError(f"Preset '{preset_id}' does not exist.")
        return preset

    def list_presets(self, strategy_id: Optional[str] = None) -> List[StrategyPreset]:
        """Lists all presets, optionally filtered by strategy_id."""
        presets = list(self._in_memory_presets.values())
        if strategy_id:
            presets = [p for p in presets if p.strategy_id == strategy_id]
        return sorted(presets, key=lambda x: x.preset_id)

    def clone_preset(
        self,
        source_preset_id: str,
        new_preset_id: str,
        new_preset_name: str,
        new_parameters: Optional[Dict[str, Any]] = None,
    ) -> StrategyPreset:
        """
        Clones an existing preset with optional parameter modifications,
        producing a new distinct preset with its own configuration hash.
        """
        source = self.get(source_preset_id)
        merged_params = dict(source.parameters)
        if new_parameters:
            merged_params.update(new_parameters)

        cloned = StrategyPreset(
            preset_id=new_preset_id,
            preset_name=new_preset_name,
            strategy_id=source.strategy_id,
            strategy_version=source.strategy_version,
            parameters=merged_params,
            risk_config_reference=source.risk_config_reference,
            execution_config_reference=source.execution_config_reference,
            is_immutable=True,
            locked_by_run=None,
        )
        self.save(cloned)
        return cloned

    def lock_preset(self, preset_id: str, run_id: str) -> None:
        """Locks a preset to guarantee it can never be modified because it is bound to a run."""
        preset = self.get(preset_id)
        preset.locked_by_run = run_id
        preset.is_immutable = True
        self.save(preset, allow_overwrite=True)
        logger.info(f"Preset '{preset_id}' locked by run '{run_id}'.")
