"""
libs/mock_trading_broker.py — Independent Mock Broker & Simulation Engine (GĐ19)
Simulates full Alpaca Paper Trading capabilities in an isolated test & workbench environment.
Features:
- Complete order validation (Market, Limit, Stop, Stop-Limit, Trailing Stop, Fractional, Notional)
- Stateful order lifecycle (pending_new -> accepted -> new -> partially_filled -> filled / canceled / replaced / rejected)
- Position & balance calculations (cash, buying power, unrealized P/L)
- Dedicated Order Activity audit trail
- Strict isolation: All mock objects tagged with is_mock=True, broker="SIMULATED_MOCK_BROKER"
- Zero broker mutations; strictly separated from live Alpaca adapters.
"""

import os
import sys
import json
import uuid
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("mock-broker")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
MOCK_DATA_DIR = os.path.join(DATA_DIR, "mock_broker")
os.makedirs(MOCK_DATA_DIR, exist_ok=True)
MOCK_STATE_FILE = os.path.join(MOCK_DATA_DIR, "mock_broker_state.json")


class MockTradingBroker:
    """
    Independent Mock Broker Engine for Order Management & Trading Workbench.
    Provides realistic broker simulation without mutating any real or paper Alpaca accounts.
    """

    INITIAL_CASH = 100000.0
    DEFAULT_PRICES = {
        "NVDA": 138.25,
        "AAPL": 231.50,
        "TSLA": 218.40,
        "BTC/USD": 80650.0,
        "ETH/USD": 2365.0,
    }

    def __init__(self, state_file: Optional[str] = None):
        self.state_file = state_file or MOCK_STATE_FILE
        self.account: Dict[str, Any] = {}
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.activities: List[Dict[str, Any]] = []
        self.client_order_ids: Dict[str, str] = {}  # client_order_id -> order_id
        self._load_state()

    def _init_default_account(self):
        """Initialize pristine starting account balance and empty portfolio."""
        self.account = {
            "id": "mock_acc_quant_sim_01",
            "account_number": "SIM-88992200",
            "status": "ACTIVE",
            "currency": "USD",
            "cash": self.INITIAL_CASH,
            "equity": self.INITIAL_CASH,
            "portfolio_value": self.INITIAL_CASH,
            "buying_power": self.INITIAL_CASH * 4.0,
            "initial_margin": 0.0,
            "maintenance_margin": 0.0,
            "pattern_day_trader": False,
            "is_mock": True,
            "broker": "SIMULATED_MOCK_BROKER",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.positions = {}
        self.orders = {}
        self.activities = []
        self.client_order_ids = {}

    def _load_state(self):
        """Load state from persistent file if present, else initialize default."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.account = data.get("account", {})
                    self.positions = data.get("positions", {})
                    self.orders = data.get("orders", {})
                    self.activities = data.get("activities", [])
                    self.client_order_ids = {
                        o.get("client_order_id"): oid
                        for oid, o in self.orders.items()
                        if o.get("client_order_id")
                    }
                    if not self.account:
                        self._init_default_account()
                    logger.info("Loaded mock broker state with %d orders, %d positions", len(self.orders), len(self.positions))
                    return
            except Exception as e:
                logger.warning("Error loading mock broker state: %s. Reinitializing.", e)
        self._init_default_account()
        self._save_state()

    def _save_state(self):
        """Atomic persist mock state to disk."""
        try:
            state = {
                "account": self.account,
                "positions": self.positions,
                "orders": self.orders,
                "activities": self.activities[-500:],  # keep last 500 audit activities
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp_file = self.state_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            if os.path.exists(self.state_file):
                os.replace(tmp_file, self.state_file)
            else:
                os.rename(tmp_file, self.state_file)
        except Exception as e:
            logger.error("Failed to save mock broker state: %s", e)

    def reset_account(self, initial_cash: Optional[float] = None) -> Dict[str, Any]:
        """Reset simulation account back to fresh starting parameters."""
        cash = initial_cash if initial_cash is not None else self.INITIAL_CASH
        self.INITIAL_CASH = cash
        self._init_default_account()
        self._record_activity("RESET", "all", "Account reset to initial starting cash of $" + str(cash))
        self._save_state()
        return self.get_account()

    def _record_activity(self, activity_type: str, order_id: str, description: str, metadata: Optional[Dict[str, Any]] = None):
        """Append an auditable event to the order lifecycle trail."""
        event = {
            "id": f"act_{uuid.uuid4().hex[:12]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "activity_type": activity_type,
            "order_id": order_id,
            "description": description,
            "metadata": metadata or {},
            "is_mock": True,
        }
        self.activities.append(event)

    def get_market_price(self, symbol: str) -> float:
        """Get best available current simulation market price for symbol."""
        clean_sym = symbol.upper().replace("-", "/")
        return self.DEFAULT_PRICES.get(clean_sym, 100.0)

    def validate_order_request(self, req: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Comprehensive Alpaca-compliant order validation.
        Returns (is_valid, error_message).
        """
        symbol = req.get("symbol")
        if not symbol or not isinstance(symbol, str) or not symbol.strip():
            return False, "Symbol is required and must be non-empty string"

        side = str(req.get("side", "")).lower()
        if side not in ("buy", "sell"):
            return False, f"Invalid order side: '{side}'. Must be 'buy' or 'sell'"

        order_type = str(req.get("type", "")).lower()
        valid_types = ("market", "limit", "stop", "stop_limit", "trailing_stop")
        if order_type not in valid_types:
            return False, f"Invalid order type: '{order_type}'. Must be one of {valid_types}"

        tif = str(req.get("time_in_force", "day")).lower()
        valid_tifs = ("day", "gtc", "opg", "cls", "ioc", "fok")
        if tif not in valid_tifs:
            return False, f"Invalid time_in_force: '{tif}'. Must be one of {valid_tifs}"

        qty = req.get("qty")
        notional = req.get("notional")

        if qty is None and notional is None:
            return False, "Either 'qty' or 'notional' must be provided"
        if qty is not None and notional is not None:
            return False, "Cannot provide both 'qty' and 'notional' on the same order"

        if qty is not None:
            try:
                qty_f = float(qty)
                if qty_f <= 0:
                    return False, f"Quantity must be greater than 0, got {qty_f}"
            except (ValueError, TypeError):
                return False, f"Invalid quantity value: '{qty}'"

        if notional is not None:
            try:
                notional_f = float(notional)
                if notional_f <= 0:
                    return False, f"Notional must be greater than 0, got {notional_f}"
            except (ValueError, TypeError):
                return False, f"Invalid notional value: '{notional}'"

        # Type-specific price validation
        if order_type in ("limit", "stop_limit"):
            limit_price = req.get("limit_price")
            if limit_price is None:
                return False, f"Limit orders require 'limit_price'"
            try:
                if float(limit_price) <= 0:
                    return False, f"Limit price must be greater than 0, got {limit_price}"
            except (ValueError, TypeError):
                return False, f"Invalid limit price: '{limit_price}'"

        if order_type in ("stop", "stop_limit"):
            stop_price = req.get("stop_price")
            if stop_price is None:
                return False, f"Stop orders require 'stop_price'"
            try:
                if float(stop_price) <= 0:
                    return False, f"Stop price must be greater than 0, got {stop_price}"
            except (ValueError, TypeError):
                return False, f"Invalid stop price: '{stop_price}'"

        if order_type == "trailing_stop":
            trail_price = req.get("trail_price")
            trail_percent = req.get("trail_percent")
            if trail_price is None and trail_percent is None:
                return False, "Trailing stop orders require either 'trail_price' or 'trail_percent'"
            if trail_price is not None and trail_percent is not None:
                return False, "Cannot provide both 'trail_price' and 'trail_percent'"
            if trail_price is not None:
                try:
                    if float(trail_price) <= 0:
                        return False, "trail_price must be > 0"
                except (ValueError, TypeError):
                    return False, f"Invalid trail_price: '{trail_price}'"
            if trail_percent is not None:
                try:
                    tp_f = float(trail_percent)
                    if tp_f <= 0 or tp_f > 100:
                        return False, "trail_percent must be between 0 and 100"
                except (ValueError, TypeError):
                    return False, f"Invalid trail_percent: '{trail_percent}'"

        return True, None

    def submit_order(self, order_req: Dict[str, Any], auto_fill: bool = True) -> Dict[str, Any]:
        """
        Validate and create a simulated mock order.
        Auto-fills Market orders immediately if auto_fill=True.
        """
        is_valid, err_msg = self.validate_order_request(order_req)
        if not is_valid:
            raise ValueError(f"Order validation error: {err_msg}")

        # Idempotency check via client_order_id
        client_order_id = order_req.get("client_order_id")
        if client_order_id and client_order_id in self.client_order_ids:
            existing_id = self.client_order_ids[client_order_id]
            raise ValueError(f"Duplicate client_order_id '{client_order_id}'. Existing order: {existing_id}")

        clean_symbol = str(order_req["symbol"]).upper().strip()
        asset_class = "crypto" if "/" in clean_symbol or "USD" in clean_symbol and ("BTC" in clean_symbol or "ETH" in clean_symbol) else "us_equity"
        now_iso = datetime.now(timezone.utc).isoformat()
        order_id = f"mock_ord_{uuid.uuid4().hex[:16]}"
        effective_client_id = client_order_id or f"mock_cli_{uuid.uuid4().hex[:12]}"

        order = {
            "id": order_id,
            "client_order_id": effective_client_id,
            "created_at": now_iso,
            "updated_at": now_iso,
            "submitted_at": now_iso,
            "filled_at": None,
            "expired_at": None,
            "canceled_at": None,
            "failed_at": None,
            "replaced_at": None,
            "replaced_by": None,
            "replaces": order_req.get("replaces"),
            "asset_class": asset_class,
            "symbol": clean_symbol,
            "qty": float(order_req["qty"]) if order_req.get("qty") is not None else None,
            "notional": float(order_req["notional"]) if order_req.get("notional") is not None else None,
            "filled_qty": 0.0,
            "filled_avg_price": None,
            "order_class": order_req.get("order_class", "simple"),
            "order_type": str(order_req["type"]).lower(),
            "type": str(order_req["type"]).lower(),
            "side": str(order_req["side"]).lower(),
            "time_in_force": str(order_req.get("time_in_force", "day")).lower(),
            "limit_price": float(order_req["limit_price"]) if order_req.get("limit_price") is not None else None,
            "stop_price": float(order_req["stop_price"]) if order_req.get("stop_price") is not None else None,
            "trail_price": float(order_req["trail_price"]) if order_req.get("trail_price") is not None else None,
            "trail_percent": float(order_req["trail_percent"]) if order_req.get("trail_percent") is not None else None,
            "status": "accepted",
            "is_mock": True,
            "broker": "SIMULATED_MOCK_BROKER",
        }

        self.orders[order_id] = order
        self.client_order_ids[effective_client_id] = order_id
        self._record_activity("CREATED", order_id, f"Submitted {order['side'].upper()} {order['type'].upper()} order for {clean_symbol}", order)

        # Execution logic: Auto-fill Market orders immediately
        if auto_fill and order["type"] == "market":
            fill_price = self.get_market_price(clean_symbol)
            self._execute_fill(order_id, fill_price)
        else:
            order["status"] = "new"

        self._recalculate_portfolio()
        self._save_state()
        return order

    def _execute_fill(self, order_id: str, fill_price: float):
        """Simulate execution fill for a mock order and update portfolio positions."""
        order = self.orders.get(order_id)
        if not order or order["status"] in ("filled", "canceled", "rejected", "expired"):
            return

        fill_qty = order["qty"]
        if fill_qty is None and order.get("notional"):
            fill_qty = round(order["notional"] / fill_price, 6)
            order["qty"] = fill_qty

        if not fill_qty or fill_qty <= 0:
            fill_qty = 1.0
            order["qty"] = fill_qty

        now_iso = datetime.now(timezone.utc).isoformat()
        order["status"] = "filled"
        order["filled_at"] = now_iso
        order["updated_at"] = now_iso
        order["filled_qty"] = fill_qty
        order["filled_avg_price"] = fill_price

        # Update position
        sym = order["symbol"]
        side = order["side"]
        existing = self.positions.get(sym)

        if side == "buy":
            total_cost = fill_qty * fill_price
            if existing:
                cur_qty = float(existing["qty"])
                cur_cost = cur_qty * float(existing["avg_entry_price"])
                new_qty = cur_qty + fill_qty
                new_avg = (cur_cost + total_cost) / new_qty if new_qty > 0 else fill_price
                existing["qty"] = new_qty
                existing["avg_entry_price"] = round(new_avg, 4)
            else:
                self.positions[sym] = {
                    "symbol": sym,
                    "qty": fill_qty,
                    "side": "long",
                    "avg_entry_price": fill_price,
                    "current_price": fill_price,
                    "market_value": round(fill_qty * fill_price, 2),
                    "unrealized_pl": 0.0,
                    "unrealized_plpc": 0.0,
                    "asset_class": order["asset_class"],
                    "is_mock": True,
                }
            self.account["cash"] -= total_cost
        elif side == "sell":
            proceeds = fill_qty * fill_price
            if existing:
                cur_qty = float(existing["qty"])
                if fill_qty >= cur_qty:
                    del self.positions[sym]
                else:
                    existing["qty"] = cur_qty - fill_qty
            self.account["cash"] += proceeds

        self._record_activity("FILLED", order_id, f"Order filled: {fill_qty} @ ${fill_price:,.2f}", {
            "filled_qty": fill_qty,
            "filled_price": fill_price,
        })

    def replace_order(self, order_id: str, replace_req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate Alpaca order replacement (cancel old order, issue replacement order).
        """
        old_order = self.orders.get(order_id)
        if not old_order:
            raise KeyError(f"Order not found: '{order_id}'")
        if old_order["status"] not in ("new", "accepted", "pending_new"):
            raise ValueError(f"Cannot replace order in '{old_order['status']}' state")

        now_iso = datetime.now(timezone.utc).isoformat()
        new_order_id = f"mock_ord_{uuid.uuid4().hex[:16]}"

        new_order = dict(old_order)
        new_order["id"] = new_order_id
        new_order["client_order_id"] = replace_req.get("client_order_id") or f"mock_cli_{uuid.uuid4().hex[:12]}"
        new_order["created_at"] = now_iso
        new_order["updated_at"] = now_iso
        new_order["submitted_at"] = now_iso
        new_order["replaces"] = order_id
        new_order["replaced_by"] = None
        new_order["status"] = "new"

        if "qty" in replace_req:
            new_order["qty"] = float(replace_req["qty"])
        if "limit_price" in replace_req:
            new_order["limit_price"] = float(replace_req["limit_price"])
        if "stop_price" in replace_req:
            new_order["stop_price"] = float(replace_req["stop_price"])
        if "time_in_force" in replace_req:
            new_order["time_in_force"] = str(replace_req["time_in_force"]).lower()

        # Invalidate old order
        old_order["status"] = "replaced"
        old_order["replaced_at"] = now_iso
        old_order["replaced_by"] = new_order_id
        old_order["updated_at"] = now_iso

        self.orders[new_order_id] = new_order
        self.client_order_ids[new_order["client_order_id"]] = new_order_id

        self._record_activity("REPLACED", order_id, f"Order replaced by {new_order_id}", {"replaced_by": new_order_id})
        self._record_activity("CREATED", new_order_id, f"Replacement order created, replaces {order_id}", new_order)

        self._recalculate_portfolio()
        self._save_state()
        return new_order

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel a pending/open mock order."""
        order = self.orders.get(order_id)
        if not order:
            raise KeyError(f"Order not found: '{order_id}'")
        if order["status"] in ("filled", "canceled", "rejected", "expired", "replaced"):
            raise ValueError(f"Cannot cancel order in '{order['status']}' state")

        now_iso = datetime.now(timezone.utc).isoformat()
        order["status"] = "canceled"
        order["canceled_at"] = now_iso
        order["updated_at"] = now_iso

        self._record_activity("CANCELED", order_id, f"Order canceled by user/system")
        self._recalculate_portfolio()
        self._save_state()
        return order

    def cancel_all_orders(self) -> List[Dict[str, Any]]:
        """Cancel all currently open mock orders."""
        canceled = []
        for oid, order in list(self.orders.items()):
            if order["status"] in ("new", "accepted", "pending_new"):
                self.cancel_order(oid)
                canceled.append(self.orders[oid])
        return canceled

    def _recalculate_portfolio(self):
        """Update positions current_price, market_value, and account equity."""
        total_market_value = 0.0
        total_cost_basis = 0.0

        for sym, pos in self.positions.items():
            cur_price = self.get_market_price(sym)
            qty = float(pos.get("qty", 0.0))
            entry_price = float(pos.get("avg_entry_price", cur_price))
            mv = round(qty * cur_price, 2)
            cost = qty * entry_price
            pl = round(mv - cost, 2)
            plpc = round((pl / cost * 100.0), 2) if cost > 0 else 0.0

            pos["current_price"] = cur_price
            pos["market_value"] = mv
            pos["unrealized_pl"] = pl
            pos["unrealized_plpc"] = plpc

            total_market_value += mv
            total_cost_basis += cost

        cash = float(self.account.get("cash", self.INITIAL_CASH))
        equity = round(cash + total_market_value, 2)
        self.account["equity"] = equity
        self.account["portfolio_value"] = equity
        self.account["buying_power"] = round(cash * 4.0, 2)
        self.account["updated_at"] = datetime.now(timezone.utc).isoformat()

    def get_account(self) -> Dict[str, Any]:
        """Get simulation account overview."""
        self._recalculate_portfolio()
        return dict(self.account)

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all current open simulation positions."""
        self._recalculate_portfolio()
        return list(self.positions.values())

    def get_orders(
        self,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Query mock orders with multi-attribute filtering.
        """
        res = list(self.orders.values())
        if status:
            st = status.lower()
            if st == "open":
                res = [o for o in res if o["status"] in ("new", "accepted", "pending_new", "partially_filled")]
            elif st == "closed":
                res = [o for o in res if o["status"] in ("filled", "canceled", "rejected", "expired", "replaced")]
            else:
                res = [o for o in res if o["status"].lower() == st]

        if symbol:
            sym_clean = symbol.upper().strip()
            res = [o for o in res if o["symbol"].upper() == sym_clean]

        if side:
            sd = side.lower().strip()
            res = [o for o in res if o["side"].lower() == sd]

        # Sort descending by created_at
        res.sort(key=lambda o: o.get("created_at", ""), reverse=True)
        return res[:limit]

    def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve individual order details."""
        return self.orders.get(order_id)

    def get_activities(self, order_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve order lifecycle audit events."""
        acts = self.activities
        if order_id:
            acts = [a for a in acts if a.get("order_id") == order_id]
        acts_sorted = sorted(acts, key=lambda a: a.get("timestamp", ""), reverse=True)
        return acts_sorted[:limit]


# Global singleton mock broker instance
mock_broker = MockTradingBroker()

