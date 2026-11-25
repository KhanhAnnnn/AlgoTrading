"""
libs/bot/portfolio_store.py — Simulation Portfolio Persistence Store (GĐ32)
Manages atomic disk persistence, snapshot versioning, and recovery for Simulation Portfolios.
All data is stored strictly in data/paper_bot/portfolios/ isolated from Mock Broker and Alpaca.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional
import json
import os
import hashlib
from datetime import datetime, timezone

from libs.bot.domain import PortfolioSnapshot, SimulatedPosition, PortfolioTransactionEvent
from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.portfolio.accounting import to_decimal


class PortfolioStore:
    """
    Handles atomic persistence and state restoration of SimulationPortfolios.
    """

    def __init__(self, storage_dir: str = "data/paper_bot/portfolios"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_path(self, portfolio_id: str) -> str:
        return os.path.join(self.storage_dir, f"{portfolio_id}.json")

    def save(self, portfolio: SimulationPortfolioManager) -> str:
        """
        Atomically saves portfolio state and latest snapshot to JSON file with SHA-256 checksum.
        Returns the absolute file path.
        """
        snapshot = portfolio.get_portfolio_snapshot()
        file_path = self._get_path(portfolio.portfolio_id)
        temp_path = f"{file_path}.tmp"

        payload = {
            "portfolio_id": portfolio.portfolio_id,
            "bot_session_id": portfolio.bot_session_id,
            "state": portfolio.state,
            "version": portfolio._version,
            "cash": float(portfolio.cash),
            "reserved_cash": float(portfolio.reserved_cash),
            "available_cash": float(portfolio.available_cash),
            "equity": float(portfolio.get_equity()),
            "peak_equity": float(portfolio.peak_equity),
            "realized_pnl": float(portfolio.realized_pnl),
            "positions": {
                sym: {
                    "symbol": p.symbol,
                    "qty": p.qty,
                    "avg_entry_price": p.avg_entry_price,
                    "current_price": p.current_price,
                    "cost_basis": p.cost_basis,
                    "market_value": p.market_value,
                    "unrealized_pnl": p.unrealized_pnl,
                    "realized_pnl": p.realized_pnl,
                }
                for sym, p in portfolio.positions.get_all_positions().items()
            },
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "checksum": snapshot.checksum,
            "environment": "SIMULATION",
        }

        # Write to temporary file first for atomic commit
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        # Atomic rename
        os.replace(temp_path, file_path)
        return file_path

    def load(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        """Loads and returns the raw portfolio state dictionary from disk."""
        file_path = self._get_path(portfolio_id)
        if not os.path.exists(file_path):
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate environment tag
        if data.get("environment") != "SIMULATION":
            raise ValueError(f"Corrupt data: portfolio {portfolio_id} is not tagged SIMULATION")

        return data

    def restore_manager(self, portfolio_id: str) -> Optional[SimulationPortfolioManager]:
        """Restores a SimulationPortfolioManager instance from persistent disk state."""
        data = self.load(portfolio_id)
        if not data:
            return None

        manager = SimulationPortfolioManager(
            portfolio_id=data["portfolio_id"],
            bot_session_id=data["bot_session_id"],
            initial_cash=data["cash"],
        )
        manager._cash = to_decimal(data["cash"])
        manager._reserved_cash = to_decimal(data.get("reserved_cash", 0.0))
        manager._realized_pnl = to_decimal(data.get("realized_pnl", 0.0))
        manager._peak_equity = to_decimal(data.get("peak_equity", data["cash"]))
        manager.state = data.get("state", "ACTIVE")
        manager._version = data.get("version", 1)

        # Restore positions
        for sym, p_data in data.get("positions", {}).items():
            if abs(p_data["qty"]) > 1e-9:
                manager.positions._positions[sym] = SimulatedPosition(
                    symbol=sym,
                    qty=p_data["qty"],
                    avg_entry_price=p_data["avg_entry_price"],
                    current_price=p_data["current_price"],
                    cost_basis=p_data["cost_basis"],
                    market_value=p_data["market_value"],
                    unrealized_pnl=p_data["unrealized_pnl"],
                    realized_pnl=p_data["realized_pnl"],
                    environment="SIMULATION",
                )

        return manager
