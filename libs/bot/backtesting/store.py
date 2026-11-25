"""
libs/bot/backtesting/store.py — Isolated Backtest Result Persistence (GĐ36)
Persists backtest configurations, metrics, equity curves, orders, and fills in isolated storage.
Guarantees complete filesystem segregation from running BotSessions and natural market topics.
"""

from typing import List, Dict, Any, Optional
import os
import json
import logging
import shutil

from libs.bot.backtesting.results import BacktestResult
from libs.bot.backtesting.config import BacktestConfig

logger = logging.getLogger("backtest-store")


class BacktestStore:
    """
    Manages filesystem persistence of historical backtest runs.
    Default directory: data/paper_bot/backtests/{run_id}/
    """

    def __init__(self, base_dir: str = "data/paper_bot/backtests"):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def _run_dir(self, run_id: str) -> str:
        return os.path.join(self.base_dir, run_id)

    def save_result(self, result: BacktestResult) -> str:
        """
        Atomically saves complete backtest outputs into a run-specific isolated directory.
        """
        r_dir = self._run_dir(result.run_id)
        os.makedirs(r_dir, exist_ok=True)

        # 1. Save summary result.json
        with open(os.path.join(r_dir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

        # 2. Save config.json
        with open(os.path.join(r_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(result.config.to_dict(), f, indent=2)

        # 3. Save metrics.json
        with open(os.path.join(r_dir, "metrics.json"), "w", encoding="utf-8") as f:
            json.dump(result.metrics, f, indent=2)

        # 4. Save equity_curve.json
        with open(os.path.join(r_dir, "equity_curve.json"), "w", encoding="utf-8") as f:
            json.dump(result.equity_curve, f, indent=2)

        # 5. Save drawdown_curve.json
        with open(os.path.join(r_dir, "drawdown_curve.json"), "w", encoding="utf-8") as f:
            json.dump(result.drawdown_curve, f, indent=2)

        # 6. Save orders.json
        with open(os.path.join(r_dir, "orders.json"), "w", encoding="utf-8") as f:
            json.dump(result.orders, f, indent=2)

        # 7. Save fills.json
        with open(os.path.join(r_dir, "fills.json"), "w", encoding="utf-8") as f:
            json.dump(result.fills, f, indent=2)

        # 8. Save GĐ41 chart & ledger artifacts (signals, decisions, bars, indicators, transactions, closed_trades, manifest)
        extra_artifacts = {
            "signals.json": result.signals,
            "decisions.json": result.decisions,
            "bars.json": result.bars,
            "indicators.json": result.indicators,
            "transactions.json": result.portfolio_transactions,
            "closed_trades.json": result.closed_trades,
            "gaps.json": result.gaps,
        }
        if result.manifest and hasattr(result.manifest, "to_dict"):
            extra_artifacts["manifest.json"] = result.manifest.to_dict()

        for fname, payload in extra_artifacts.items():
            with open(os.path.join(r_dir, fname), "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

        logger.info(f"Saved backtest run '{result.run_id}' to {r_dir}")
        return r_dir

    def _read_json_file(self, run_id: str, filename: str, default: Any) -> Any:
        path = os.path.join(self._run_dir(run_id), filename)
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, result: BacktestResult) -> str:
        """Alias for save_result."""
        return self.save_result(result)

    def get_result(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Loads result summary dictionary for a backtest run."""
        path = os.path.join(self._run_dir(run_id), "result.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_equity_curve(self, run_id: str) -> List[Dict[str, Any]]:
        """Loads equity curve points for a backtest run."""
        path = os.path.join(self._run_dir(run_id), "equity_curve.json")
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_trades(self, run_id: str) -> List[Dict[str, Any]]:
        """Loads fills/trades for a backtest run."""
        path = os.path.join(self._run_dir(run_id), "fills.json")
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_orders(self, run_id: str) -> List[Dict[str, Any]]:
        """Loads simulated orders for a backtest run."""
        return self._read_json_file(run_id, "orders.json", [])

    def get_signals(self, run_id: str) -> List[Dict[str, Any]]:
        """Loads recorded strategy signals for a backtest run."""
        return self._read_json_file(run_id, "signals.json", [])

    def get_decisions(self, run_id: str) -> List[Dict[str, Any]]:
        """Loads risk/decision records for a backtest run."""
        return self._read_json_file(run_id, "decisions.json", [])

    def get_bars(self, run_id: str) -> List[Dict[str, Any]]:
        """Loads historical OHLCV bars for a backtest run."""
        return self._read_json_file(run_id, "bars.json", [])

    def get_indicators(self, run_id: str) -> Dict[str, Any]:
        """Loads indicator series for a backtest run."""
        return self._read_json_file(run_id, "indicators.json", {})

    def get_transactions(self, run_id: str) -> List[Dict[str, Any]]:
        """Loads portfolio cash/ledger transactions for a backtest run."""
        return self._read_json_file(run_id, "transactions.json", [])

    def get_closed_trades(self, run_id: str) -> List[Dict[str, Any]]:
        """Loads matched entry/exit closed trade associations."""
        return self._read_json_file(run_id, "closed_trades.json", [])

    def get_manifest(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Loads pinned dataset manifest for a backtest run."""
        return self._read_json_file(run_id, "manifest.json", None)

    def get_gaps(self, run_id: str) -> List[Dict[str, Any]]:
        """Loads detected bar gaps for a backtest run."""
        return self._read_json_file(run_id, "gaps.json", [])

    def list_runs(self) -> List[Dict[str, Any]]:
        """Lists all completed and stored backtest runs."""
        runs = []
        if not os.path.exists(self.base_dir):
            return []

        for entry in os.listdir(self.base_dir):
            r_dir = os.path.join(self.base_dir, entry)
            if os.path.isdir(r_dir):
                res_path = os.path.join(r_dir, "result.json")
                if os.path.exists(res_path):
                    try:
                        with open(res_path, "r", encoding="utf-8") as f:
                            runs.append(json.load(f))
                    except Exception as e:
                        logger.warning(f"Failed to read backtest result in {res_path}: {e}")

        # Sort descending by completion/start time
        runs.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return runs

    def delete_run(self, run_id: str) -> bool:
        """Removes a backtest run directory from storage."""
        r_dir = self._run_dir(run_id)
        if os.path.exists(r_dir):
            shutil.rmtree(r_dir)
            logger.info(f"Deleted backtest run {run_id}")
            return True
        return False
