"""
libs/alpaca_paper_gate.py — Alpaca Paper Execution Gate & Read-Only Synchronization Adapter (GĐ21)
Enforces:
1. Strict paper-only base URL validation (fails closed if live URL detected).
2. Fail-closed execution gate: Direct order placement/modification/cancellation to Alpaca Paper is locked.
3. Fake transport mode for safe unit & integration testing of write paths without sending network requests.
4. Rich read-only telemetry synchronization: Account, Positions, Orders, Order Details, Activities.
5. Strict tagging: Every entity explicitly tagged with data_source ("ALPACA_PAPER" or "ALPACA_PAPER_FAKE").
"""

import os
import sys
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timezone
import requests

# Base directories
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LIBS_DIR = os.path.join(BASE_DIR, 'libs')
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

try:
    from alpaca_config.keys import config
except ImportError:
    config = {}

logger = logging.getLogger("AlpacaPaperGate")


class PaperExecutionGateClosedError(Exception):
    """Raised when an order write operation is attempted while Paper Execution Gate is locked."""
    pass


class LiveTradingProhibitedError(Exception):
    """Raised when any endpoint or configuration indicates live trading."""
    pass


class BrokerMode:
    """Explicit Operational Modes for System Architecture (GĐ22)."""
    MOCK = "MOCK"
    ALPACA_PAPER_READ_ONLY = "ALPACA_PAPER_READ_ONLY"
    ALPACA_PAPER_EXECUTION = "ALPACA_PAPER_EXECUTION"


class AlpacaPaperGate:
    """
    Dedicated Adapter for Alpaca Paper Trading.
    Separates read-only synchronization from execution guards.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        key_id: Optional[str] = None,
        secret_key: Optional[str] = None,
        is_gate_open: bool = False,
        mode: str = BrokerMode.ALPACA_PAPER_READ_ONLY
    ):
        self.base_url = base_url if base_url is not None else config.get(
            'trade_api_base_url',
            os.environ.get('ALPACA_TRADE_BASE_URL', 'https://paper-api.alpaca.markets')
        )
        self.key_id = key_id if key_id is not None else config.get('key_id', os.environ.get('ALPACA_KEY_ID', ''))
        self.secret_key = secret_key if secret_key is not None else config.get('secret_key', os.environ.get('ALPACA_SECRET_KEY', ''))
        
        # In GĐ22, is_gate_open is STRICTLY False by default
        self.is_gate_open = is_gate_open
        self.mode = mode

        # Security check: Base URL must strictly be paper-api
        self._verify_safety_invariants()

    def _verify_safety_invariants(self):
        """Asserts that base URL is strictly paper and never live."""
        if not self.base_url:
            raise PaperExecutionGateClosedError("BASE_URL missing. Fail-closed enforced.")
        
        url_lower = self.base_url.lower()
        if "api.alpaca.markets" in url_lower and "paper" not in url_lower:
            raise LiveTradingProhibitedError(
                f"CRITICAL SECURITY VIOLATION: Endpoint '{self.base_url}' points to Live Alpaca! "
                "Only 'https://paper-api.alpaca.markets' is permitted."
            )

    def _get_headers(self) -> Dict[str, str]:
        return {
            'APCA-API-KEY-ID': self.key_id,
            'APCA-API-SECRET-KEY': self.secret_key,
            'Content-Type': 'application/json',
        }

    # =========================================================================
    # Part 1: Read-Only Synchronization (GĐ21.1)
    # =========================================================================

    def get_account_overview(self) -> Dict[str, Any]:
        """Fetch read-only account telemetry directly from Alpaca Paper."""
        self._verify_safety_invariants()
        if not self.key_id or not self.secret_key:
            return {"status": "UNCONFIGURED", "data_source": "ALPACA_PAPER", "is_mock": False}

        try:
            resp = requests.get(f"{self.base_url}/v2/account", headers=self._get_headers(), timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "id": data.get("id"),
                    "account_number": data.get("account_number"),
                    "status": data.get("status", "ACTIVE"),
                    "currency": data.get("currency", "USD"),
                    "cash": float(data.get("cash", 0.0)),
                    "equity": float(data.get("equity", 0.0)),
                    "buying_power": float(data.get("buying_power", 0.0)),
                    "portfolio_value": float(data.get("portfolio_value", 0.0)),
                    "pattern_day_trader": data.get("pattern_day_trader", False),
                    "created_at": data.get("created_at"),
                    "data_source": "ALPACA_PAPER",
                    "broker": "ALPACA_PAPER",
                    "is_mock": False,
                    "gate_status": "OPEN" if self.is_gate_open else "CLOSED",
                    "synced_at": datetime.now(timezone.utc).isoformat()
                }
            return {
                "status": f"ERROR_{resp.status_code}",
                "error": resp.text,
                "data_source": "ALPACA_PAPER",
                "is_mock": False
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "data_source": "ALPACA_PAPER",
                "is_mock": False
            }

    def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch read-only positions directly from Alpaca Paper."""
        self._verify_safety_invariants()
        if not self.key_id or not self.secret_key:
            return []

        try:
            resp = requests.get(f"{self.base_url}/v2/positions", headers=self._get_headers(), timeout=5)
            if resp.status_code == 200:
                res = []
                for p in resp.json():
                    res.append({
                        "symbol": p.get("symbol"),
                        "qty": float(p.get("qty", 0.0)),
                        "side": p.get("side"),
                        "current_price": float(p.get("current_price", 0.0)),
                        "avg_entry_price": float(p.get("avg_entry_price", 0.0)),
                        "market_value": float(p.get("market_value", 0.0)),
                        "unrealized_pl": float(p.get("unrealized_pl", 0.0)),
                        "unrealized_plpc": float(p.get("unrealized_plpc", 0.0)),
                        "data_source": "ALPACA_PAPER",
                        "broker": "ALPACA_PAPER",
                        "is_mock": False
                    })
                return res
            return []
        except Exception:
            return []

    def get_orders(
        self,
        status: str = "all",
        limit: int = 50,
        nested: bool = True
    ) -> List[Dict[str, Any]]:
        """Fetch read-only orders directly from Alpaca Paper with filtering & pagination."""
        self._verify_safety_invariants()
        if not self.key_id or not self.secret_key:
            return []

        try:
            params = {
                "status": status,
                "limit": limit,
                "nested": str(nested).lower()
            }
            resp = requests.get(f"{self.base_url}/v2/orders", headers=self._get_headers(), params=params, timeout=5)
            if resp.status_code == 200:
                orders = []
                for o in resp.json():
                    orders.append({
                        "id": o.get("id"),
                        "client_order_id": o.get("client_order_id"),
                        "symbol": o.get("symbol"),
                        "qty": o.get("qty"),
                        "notional": o.get("notional"),
                        "filled_qty": o.get("filled_qty", "0"),
                        "filled_avg_price": o.get("filled_avg_price"),
                        "order_class": o.get("order_class", "simple"),
                        "order_type": o.get("type"),
                        "type": o.get("type"),
                        "side": o.get("side"),
                        "time_in_force": o.get("time_in_force"),
                        "limit_price": o.get("limit_price"),
                        "stop_price": o.get("stop_price"),
                        "status": o.get("status"),
                        "created_at": o.get("created_at"),
                        "submitted_at": o.get("submitted_at") or o.get("created_at"),
                        "filled_at": o.get("filled_at"),
                        "expired_at": o.get("expired_at"),
                        "canceled_at": o.get("canceled_at"),
                        "data_source": "ALPACA_PAPER",
                        "broker": "ALPACA_PAPER",
                        "is_mock": False
                    })
                return orders
            return []
        except Exception:
            return []

    def get_order_by_id(self, order_id: str) -> Dict[str, Any]:
        """Fetch detailed order status directly from Alpaca Paper."""
        self._verify_safety_invariants()
        if not self.key_id or not self.secret_key:
            return {"error": "UNCONFIGURED"}

        try:
            resp = requests.get(f"{self.base_url}/v2/orders/{order_id}", headers=self._get_headers(), timeout=5)
            if resp.status_code == 200:
                o = resp.json()
                o["data_source"] = "ALPACA_PAPER"
                o["broker"] = "ALPACA_PAPER"
                o["is_mock"] = False
                return o
            return {"error": f"HTTP {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"error": str(e)}

    def get_account_activities(self, activity_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch account activities directly from Alpaca Paper (FILL, CFEE, FEE, JNLC)."""
        self._verify_safety_invariants()
        if not self.key_id or not self.secret_key:
            return []

        try:
            url = f"{self.base_url}/v2/account/activities"
            if activity_type:
                url += f"/{activity_type}"
            params = {"page_size": limit}
            resp = requests.get(url, headers=self._get_headers(), params=params, timeout=5)
            if resp.status_code == 200:
                activities = resp.json()
                for a in activities:
                    a["data_source"] = "ALPACA_PAPER"
                    a["is_mock"] = False
                return activities
            return []
        except Exception:
            return []

    # =========================================================================
    # Part 2: Paper Execution Gate (GĐ21.3 & GĐ22)
    # =========================================================================

    def submit_paper_order(
        self,
        order_request: Dict[str, Any],
        fake_transport: bool = False
    ) -> Dict[str, Any]:
        """
        Submits order through Paper Execution Gate.
        In GĐ21:
        - If fake_transport=False: FAILS CLOSED with PaperExecutionGateClosedError.
        - If fake_transport=True: Validates schema and returns simulated confirmation.
        """
        self._verify_safety_invariants()

        if not self.is_gate_open and not fake_transport:
            raise PaperExecutionGateClosedError(
                "CRITICAL SAFETY GUARD: Alpaca Paper Execution Gate is LOCKED (fail-closed). "
                "No live or paper write operations permitted in GĐ21. Use fake_transport=True for testing."
            )

        if fake_transport:
            # Validate input schema
            symbol = order_request.get("symbol")
            side = order_request.get("side")
            order_type = order_request.get("type", "market")
            qty = order_request.get("qty")
            notional = order_request.get("notional")

            if not symbol or not side:
                raise ValueError("Both 'symbol' and 'side' are required.")
            if qty is None and notional is None:
                raise ValueError("Must provide either 'qty' or 'notional'.")
            if qty is not None and notional is not None:
                raise ValueError("Cannot specify both 'qty' and 'notional'.")

            fake_order_id = f"fake_paper_{os.urandom(6).hex()}"
            return {
                "id": fake_order_id,
                "client_order_id": order_request.get("client_order_id", f"fake_cli_{os.urandom(4).hex()}"),
                "symbol": symbol.upper(),
                "side": side.lower(),
                "type": order_type.lower(),
                "qty": str(qty) if qty is not None else None,
                "notional": str(notional) if notional is not None else None,
                "time_in_force": order_request.get("time_in_force", "day"),
                "status": "fake_accepted",
                "gate_status": "CLOSED_MOCK_TRANSPORT",
                "data_source": "ALPACA_PAPER_FAKE",
                "broker": "ALPACA_PAPER_SIMULATED",
                "is_mock": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }

        # Real execution path is permanently disabled in GĐ21
        raise PaperExecutionGateClosedError("Paper Execution Gate active execution is not approved in GĐ21.")

    def replace_paper_order(
        self,
        order_id: str,
        replace_request: Dict[str, Any],
        fake_transport: bool = False
    ) -> Dict[str, Any]:
        """Replaces an open paper order through execution gate."""
        self._verify_safety_invariants()

        if not self.is_gate_open and not fake_transport:
            raise PaperExecutionGateClosedError(
                "CRITICAL SAFETY GUARD: Alpaca Paper Order Replacement is LOCKED (fail-closed)."
            )

        if fake_transport:
            new_id = f"fake_paper_rep_{os.urandom(6).hex()}"
            return {
                "id": new_id,
                "replaces": order_id,
                "qty": str(replace_request.get("qty", "1.0")),
                "limit_price": str(replace_request.get("limit_price", "100.0")),
                "status": "fake_replaced",
                "gate_status": "CLOSED_MOCK_TRANSPORT",
                "data_source": "ALPACA_PAPER_FAKE",
                "broker": "ALPACA_PAPER_SIMULATED",
                "is_mock": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

        raise PaperExecutionGateClosedError("Paper Order Replacement active execution is not approved in GĐ21.")

    def cancel_paper_order(
        self,
        order_id: str,
        fake_transport: bool = False
    ) -> Dict[str, Any]:
        """Cancels a single paper order through execution gate."""
        self._verify_safety_invariants()

        if not self.is_gate_open and not fake_transport:
            raise PaperExecutionGateClosedError(
                "CRITICAL SAFETY GUARD: Alpaca Paper Order Cancellation is LOCKED (fail-closed)."
            )

        if fake_transport:
            return {
                "id": order_id,
                "status": "fake_canceled",
                "gate_status": "CLOSED_MOCK_TRANSPORT",
                "data_source": "ALPACA_PAPER_FAKE",
                "broker": "ALPACA_PAPER_SIMULATED",
                "is_mock": True,
                "canceled_at": datetime.now(timezone.utc).isoformat()
            }

        raise PaperExecutionGateClosedError("Paper Order Cancellation active execution is not approved in GĐ21.")

    def cancel_all_paper_orders(
        self,
        fake_transport: bool = False
    ) -> List[Dict[str, Any]]:
        """Cancels all open paper orders through execution gate."""
        self._verify_safety_invariants()

        if not self.is_gate_open and not fake_transport:
            raise PaperExecutionGateClosedError(
                "CRITICAL SAFETY GUARD: Alpaca Paper Bulk Cancellation is LOCKED (fail-closed)."
            )

        if fake_transport:
            return [
                {
                    "id": f"fake_paper_{i}",
                    "status": "fake_canceled",
                    "gate_status": "CLOSED_MOCK_TRANSPORT",
                    "data_source": "ALPACA_PAPER_FAKE",
                    "is_mock": True
                }
                for i in range(2)
            ]

        raise PaperExecutionGateClosedError("Paper Bulk Cancellation active execution is not approved in GĐ21.")


# Singleton instance for system usage
paper_gate = AlpacaPaperGate()
