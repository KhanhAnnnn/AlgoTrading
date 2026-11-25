"""
libs/bot/experiments/store.py — Persistent Storage for Backtest Experiments (GĐ38)
Stores experiment definitions, variants, and comparison results in data/paper_bot/experiments/.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import json
import os
import logging

logger = logging.getLogger("experiment-store")


class ExperimentStore:
    """
    Filesystem persistence layer for backtest experiments.
    """

    def __init__(self, storage_dir: str = "data/paper_bot/experiments"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load_all()

    def _get_path(self, experiment_id: str) -> str:
        safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in experiment_id)
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
                        exp_id = data.get("experiment_id")
                        if exp_id:
                            self._cache[exp_id] = data
                except Exception as e:
                    logger.warning(f"Failed to load experiment {fpath}: {e}")

    def save(self, experiment_data: Dict[str, Any]) -> None:
        """Persists an experiment record to disk atomically."""
        exp_id = experiment_data.get("experiment_id")
        if not exp_id:
            raise ValueError("experiment_data must contain 'experiment_id'")

        self._cache[exp_id] = experiment_data
        fpath = self._get_path(exp_id)
        temp_path = f"{fpath}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(experiment_data, f, indent=2, sort_keys=True)
        os.replace(temp_path, fpath)
        logger.info(f"Saved experiment '{exp_id}'")

    def get(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves experiment data by experiment_id."""
        return self._cache.get(experiment_id)

    def list_experiments(self) -> List[Dict[str, Any]]:
        """Lists all saved experiments."""
        return sorted(list(self._cache.values()), key=lambda x: x.get("created_at", ""), reverse=True)

    def delete(self, experiment_id: str) -> bool:
        """Deletes an experiment."""
        if experiment_id in self._cache:
            self._cache.pop(experiment_id)
            fpath = self._get_path(experiment_id)
            if os.path.exists(fpath):
                os.remove(fpath)
            return True
        return False
