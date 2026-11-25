"""
libs/bot/execution/order_manager.py — Simulation Order Manager (GĐ33)
Manages order creation from SimulationOrderIntents, lifecycle transitions,
cancellations, replacements, and in-memory indexing with persistence.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime, timezone
import uuid
import logging

from libs.bot.domain import SimulationOrderIntent, SimulatedOrder
from libs.bot.interfaces import SimulationOrderManager as ISimulationOrderManager
from libs.bot.execution.lifecycle import (
    OrderState,
    OrderLifecycleStateMachine,
    TERMINAL_STATES,
    ACTIVE_STATES,
    InvalidOrderStateTransitionError,
)
from libs.bot.execution.order_store import OrderStore
from libs.bot.portfolio.accounting import to_decimal

logger = logging.getLogger("simulation-order-manager")


class SimulationOrderManager(ISimulationOrderManager):
    """
    Manages order creation from intents and controls order lifecycle state transitions.
    Implements the SimulationOrderManager interface from GĐ29.
    """

    def __init__(self, order_store: Optional[OrderStore] = None):
        self.order_store = order_store or OrderStore()
        self._orders: Dict[str, SimulatedOrder] = {}
        self._orders_by_intent: Dict[str, SimulatedOrder] = {}
        self._seen_idempotency_keys: Set[str] = set()

    def validate_intent(self, intent: SimulationOrderIntent) -> Tuple[bool, Optional[str]]:
        """
        Validates whether an intent is admissible for order creation.
        Returns (is_valid, rejection_reason).
        """
        if intent.environment != "SIMULATION":
            return False, "NON_SIMULATION_ENVIRONMENT"

        if intent.intent_id in self._orders_by_intent:
            return False, "INTENT_ALREADY_CONSUMED"

        if intent.idempotency_key in self._seen_idempotency_keys:
            return False, "DUPLICATE_INTENT_IDEMPOTENCY_KEY"

        if not intent.symbol:
            return False, "MISSING_SYMBOL"

        if intent.side.upper() not in {"BUY", "SELL"}:
            return False, f"INVALID_SIDE_{intent.side}"

        q = to_decimal(intent.proposed_quantity)
        if q <= Decimal("0.0"):
            return False, "NON_POSITIVE_QUANTITY"

        if intent.reference_price <= 0.0:
            return False, "INVALID_REFERENCE_PRICE"

        if intent.risk_configuration_version not in {"1.0.0", "1.0", "v1.0.0"}:
            return False, f"INVALID_STRATEGY_VERSION_{intent.risk_configuration_version}"

        return True, None

    def create_order_from_intent(self, intent: SimulationOrderIntent) -> SimulatedOrder:
        """
        Transforms a validated intent into an active WORKING SimulatedOrder.
        Enforces idempotency and records state transitions.
        """
        is_valid, err = self.validate_intent(intent)
        if not is_valid:
            raise ValueError(f"Intent {intent.intent_id} rejected: {err}")

        order_id = f"sim_ord_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        order = SimulatedOrder(
            simulated_order_id=order_id,
            intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key,
            bot_session_id=intent.bot_session_id,
            symbol=intent.symbol,
            side=intent.side.upper(),
            order_type=intent.order_type.upper(),
            quantity=float(intent.proposed_quantity),
            filled_quantity=0.0,
            remaining_quantity=float(intent.proposed_quantity),
            limit_price=intent.limit_price,
            stop_price=getattr(intent, "stop_price", None),
            status=OrderState.CREATED,
            time_in_force="GTC",
            created_at=now,
            submitted_at=now,
            updated_at=now,
            environment="SIMULATION",
            metadata={
                "portfolio_id": intent.portfolio_id,
                "signal_id": intent.signal_id,
                "reference_price": intent.reference_price,
                "risk_version": intent.risk_configuration_version,
            },
        )

        # Transition CREATED -> ACCEPTED -> WORKING
        OrderLifecycleStateMachine.transition(order, OrderState.ACCEPTED)
        OrderLifecycleStateMachine.transition(order, OrderState.WORKING)

        # Indexing and persistence
        self._orders[order_id] = order
        self._orders_by_intent[intent.intent_id] = order
        self._seen_idempotency_keys.add(intent.idempotency_key)
        self.order_store.save_order(order)

        logger.info(f"Created order {order_id} ({order.side} {order.quantity} {order.symbol}) from intent {intent.intent_id}")
        return order

    def submit_order_intent(self, intent: SimulationOrderIntent) -> SimulatedOrder:
        """Implements ISimulationOrderManager.submit_order_intent."""
        return self.create_order_from_intent(intent)

    def cancel_order(self, order_id: str, reason: str = "USER_REQUESTED") -> bool:
        """
        Cancels an open order.
        Returns True if cancelled, False if order was already terminal.
        """
        order = self.get_order(order_id)
        if not order:
            logger.warning(f"Cannot cancel: order {order_id} not found")
            return False

        if order.status in TERMINAL_STATES:
            logger.warning(f"Cannot cancel: order {order_id} is already in terminal state '{order.status}'")
            return False

        OrderLifecycleStateMachine.transition(order, OrderState.CANCELLED, reason=reason)
        self.order_store.save_order(order)
        logger.info(f"Order {order_id} cancelled ({reason})")
        return True

    def replace_order(
        self,
        order_id: str,
        new_quantity: float,
        new_limit_price: Optional[float] = None,
    ) -> SimulatedOrder:
        """
        Replaces an active WORKING order with a modified order, preserving audit links.
        """
        old_order = self.get_order(order_id)
        if not old_order:
            raise ValueError(f"Cannot replace: order {order_id} not found")

        if old_order.status != OrderState.WORKING:
            raise InvalidOrderStateTransitionError(
                f"Cannot replace order {order_id} in state '{old_order.status}' (must be WORKING)"
            )

        new_order_id = f"sim_ord_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        new_order = SimulatedOrder(
            simulated_order_id=new_order_id,
            intent_id=old_order.intent_id,
            idempotency_key=f"{old_order.idempotency_key}_rep_{uuid.uuid4().hex[:6]}",
            bot_session_id=old_order.bot_session_id,
            symbol=old_order.symbol,
            side=old_order.side,
            order_type=old_order.order_type,
            quantity=new_quantity,
            filled_quantity=0.0,
            remaining_quantity=new_quantity,
            limit_price=new_limit_price if new_limit_price is not None else old_order.limit_price,
            status=OrderState.CREATED,
            time_in_force=old_order.time_in_force,
            created_at=now,
            submitted_at=now,
            updated_at=now,
            replaces_order_id=old_order.simulated_order_id,
            environment="SIMULATION",
            metadata=old_order.metadata,
        )

        # Transition old order to REPLACED
        OrderLifecycleStateMachine.transition(old_order, OrderState.REPLACED)
        old_order.replaced_by_order_id = new_order_id

        # Transition new order to WORKING
        OrderLifecycleStateMachine.transition(new_order, OrderState.ACCEPTED)
        OrderLifecycleStateMachine.transition(new_order, OrderState.WORKING)

        self._orders[new_order_id] = new_order
        self.order_store.save_order(old_order)
        self.order_store.save_order(new_order)

        logger.info(f"Replaced order {old_order.simulated_order_id} with {new_order_id}")
        return new_order

    def expire_order(self, order_id: str, reason: str = "TIME_IN_FORCE_EXPIRED") -> bool:
        """Transitions an order to EXPIRED."""
        order = self.get_order(order_id)
        if not order or order.status in TERMINAL_STATES:
            return False

        OrderLifecycleStateMachine.transition(order, OrderState.EXPIRED, reason=reason)
        self.order_store.save_order(order)
        return True

    def get_order(self, order_id: str) -> Optional[SimulatedOrder]:
        """Retrieves order by ID from memory cache or disk."""
        if order_id in self._orders:
            return self._orders[order_id]
        data = self.order_store.get_order(order_id)
        if data:
            order = self._dict_to_order(data)
            self._orders[order_id] = order
            return order
        return None

    def get_open_orders(self) -> List[SimulatedOrder]:
        """Returns all currently active (non-terminal) orders."""
        return [o for o in self._orders.values() if o.status in {OrderState.WORKING, OrderState.PARTIALLY_FILLED}]

    def get_orders_by_symbol(self, symbol: str) -> List[SimulatedOrder]:
        """Returns all orders for a specific symbol."""
        return [o for o in self._orders.values() if o.symbol == symbol]

    def _dict_to_order(self, d: Dict[str, Any]) -> SimulatedOrder:
        """Reconstructs SimulatedOrder entity from dictionary."""
        return SimulatedOrder(
            simulated_order_id=d["order_id"],
            intent_id=d.get("intent_id", ""),
            idempotency_key=d.get("idempotency_key", ""),
            bot_session_id=d.get("bot_session_id", ""),
            strategy_id=d.get("strategy_id", ""),
            strategy_version=d.get("strategy_version", "1.0.0"),
            symbol=d["symbol"],
            asset_class=d.get("asset_class", "STOCKS"),
            side=d["side"],
            order_type=d.get("order_type", "MARKET"),
            quantity=d.get("quantity", 0.0),
            filled_quantity=d.get("filled_quantity", 0.0),
            remaining_quantity=d.get("remaining_quantity", 0.0),
            limit_price=d.get("limit_price"),
            stop_price=d.get("stop_price"),
            trailing_offset=d.get("trailing_offset"),
            trailing_reference_price=d.get("trailing_reference_price"),
            average_fill_price=d.get("average_fill_price", 0.0),
            status=d.get("status", "NEW"),
            time_in_force=d.get("time_in_force", "GTC"),
            source_bar_key=d.get("source_bar_key", ""),
            rejection_reason=d.get("rejection_reason"),
            environment=d.get("environment", "SIMULATION"),
            metadata=d.get("metadata", {}),
        )
