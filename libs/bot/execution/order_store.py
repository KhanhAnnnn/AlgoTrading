"""
libs/bot/execution/order_store.py — Persistent Simulated Order Store (GĐ33)
Manages atomic disk persistence, index retrieval, and crash recovery for SimulatedOrders.
Storage location: data/paper_bot/orders/
"""

from typing import Dict, Any, List, Optional
import json
import os
from datetime import datetime, timezone

from libs.bot.domain import SimulatedOrder


class OrderStore:
    """
    Handles atomic persistence and retrieval of SimulatedOrders.
    """

    def __init__(self, storage_dir: str = "data/paper_bot/orders"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.log_path = os.path.join(self.storage_dir, "orders_log.jsonl")
        self._seen_order_ids: set[str] = set()
        self._seen_idempotency_keys: set[str] = set()
        self._load_existing_indices()

    def _load_existing_indices(self) -> None:
        """Loads order IDs and idempotency keys from log."""
        if not os.path.exists(self.log_path):
            return
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if "order_id" in record:
                            self._seen_order_ids.add(record["order_id"])
                        if "idempotency_key" in record and record["idempotency_key"]:
                            self._seen_idempotency_keys.add(record["idempotency_key"])
                    except json.JSONDecodeError:
                        continue

    def save_order(self, order: SimulatedOrder) -> str:
        """
        Atomically saves order to disk and appends to audit log.
        Returns the saved JSON file path.
        """
        payload = {
            "order_id": order.simulated_order_id,
            "intent_id": order.intent_id,
            "idempotency_key": order.idempotency_key,
            "bot_session_id": order.bot_session_id,
            "strategy_id": order.strategy_id,
            "strategy_version": order.strategy_version,
            "symbol": order.symbol,
            "asset_class": order.asset_class,
            "side": order.side,
            "order_type": order.order_type,
            "quantity": order.quantity,
            "filled_quantity": order.filled_quantity,
            "remaining_quantity": order.remaining_quantity,
            "limit_price": order.limit_price,
            "stop_price": order.stop_price,
            "trailing_offset": order.trailing_offset,
            "trailing_reference_price": order.trailing_reference_price,
            "average_fill_price": order.average_fill_price,
            "status": order.status,
            "time_in_force": order.time_in_force,
            "created_at": order.created_at.isoformat() if isinstance(order.created_at, datetime) else str(order.created_at),
            "submitted_at": order.submitted_at.isoformat() if isinstance(order.submitted_at, datetime) else str(order.submitted_at),
            "updated_at": order.updated_at.isoformat() if isinstance(order.updated_at, datetime) else str(order.updated_at),
            "source_bar_key": order.source_bar_key,
            "rejection_reason": order.rejection_reason,
            "metadata": order.metadata,
            "environment": order.environment,
        }

        file_path = os.path.join(self.storage_dir, f"{order.simulated_order_id}.json")
        temp_path = f"{file_path}.tmp"

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(temp_path, file_path)

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

        self._seen_order_ids.add(order.simulated_order_id)
        if order.idempotency_key:
            self._seen_idempotency_keys.add(order.idempotency_key)
        return file_path

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves raw order data from disk."""
        file_path = os.path.join(self.storage_dir, f"{order_id}.json")
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_all_orders(self) -> List[Dict[str, Any]]:
        """Loads all saved orders from disk for recovery."""
        orders = []
        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.storage_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    orders.append(json.load(f))
        return orders
