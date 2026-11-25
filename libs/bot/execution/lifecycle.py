"""
libs/bot/execution/lifecycle.py — Order Lifecycle State Machine (GĐ33)
Defines order states, transitions, terminal restrictions, and quantity invariants.
"""

from decimal import Decimal
from typing import Set, Dict, List, Optional
from datetime import datetime, timezone

from libs.bot.domain import SimulatedOrder
from libs.bot.portfolio.accounting import to_decimal


class OrderState:
    """Standardized order lifecycle states for AlgoTrading V2.0."""
    CREATED = "CREATED"
    NEW = "NEW"  # Backward-compatible alias for CREATED
    ACCEPTED = "ACCEPTED"
    WORKING = "WORKING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REPLACED = "REPLACED"


TERMINAL_STATES: Set[str] = {
    OrderState.FILLED,
    OrderState.CANCELLED,
    OrderState.REJECTED,
    OrderState.EXPIRED,
    OrderState.REPLACED,
}

ACTIVE_STATES: Set[str] = {
    OrderState.CREATED,
    OrderState.NEW,
    OrderState.ACCEPTED,
    OrderState.WORKING,
    OrderState.PARTIALLY_FILLED,
}


class InvalidOrderStateTransitionError(Exception):
    """Raised when an illegal order lifecycle state transition is attempted."""
    pass


class OrderLifecycleStateMachine:
    """
    Enforces valid state transitions and quantity invariants on SimulatedOrder entities.
    """

    # Allowed state transition map
    VALID_TRANSITIONS: Dict[str, Set[str]] = {
        OrderState.CREATED: {OrderState.ACCEPTED, OrderState.REJECTED, OrderState.CANCELLED},
        OrderState.NEW: {OrderState.ACCEPTED, OrderState.WORKING, OrderState.REJECTED, OrderState.CANCELLED},
        OrderState.ACCEPTED: {OrderState.WORKING, OrderState.CANCELLED, OrderState.EXPIRED, OrderState.REJECTED},
        OrderState.WORKING: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCELLED, OrderState.EXPIRED, OrderState.REPLACED},
        OrderState.PARTIALLY_FILLED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCELLED, OrderState.EXPIRED},
        OrderState.FILLED: set(),
        OrderState.CANCELLED: set(),
        OrderState.REJECTED: set(),
        OrderState.EXPIRED: set(),
        OrderState.REPLACED: set(),
    }

    @classmethod
    def can_transition(cls, current_state: str, new_state: str) -> bool:
        """Checks if a state transition is permitted."""
        allowed = cls.VALID_TRANSITIONS.get(current_state, set())
        return new_state in allowed

    @classmethod
    def transition(cls, order: SimulatedOrder, new_state: str, reason: str = "") -> None:
        """
        Executes a validated state transition on an order.
        Raises InvalidOrderStateTransitionError if transition is illegal.
        """
        curr = order.status
        if curr in TERMINAL_STATES:
            raise InvalidOrderStateTransitionError(
                f"Cannot transition order {order.simulated_order_id} from terminal state '{curr}' to '{new_state}'"
            )

        if not cls.can_transition(curr, new_state):
            raise InvalidOrderStateTransitionError(
                f"Illegal order state transition for {order.simulated_order_id}: '{curr}' -> '{new_state}'"
            )

        order.status = new_state
        order.updated_at = datetime.now(timezone.utc)
        if reason and new_state in {OrderState.REJECTED, OrderState.CANCELLED}:
            order.rejection_reason = reason

    @classmethod
    def apply_fill_to_order(
        cls,
        order: SimulatedOrder,
        fill_qty: Decimal,
        fill_price: Decimal,
    ) -> str:
        """
        Updates order filled_quantity, remaining_quantity, and average_fill_price.
        Transitions order to PARTIALLY_FILLED or FILLED.
        Returns the resulting order status.
        """
        if order.status in TERMINAL_STATES:
            raise InvalidOrderStateTransitionError(
                f"Cannot apply fill to order {order.simulated_order_id} in terminal state '{order.status}'"
            )

        q_order = to_decimal(order.quantity)
        curr_filled = to_decimal(order.filled_quantity)
        new_filled = curr_filled + fill_qty

        if new_filled > q_order + Decimal("1e-9"):
            raise ValueError(
                f"Fill quantity {fill_qty} causes total filled {new_filled} to exceed order quantity {q_order}"
            )

        new_remaining = max(Decimal("0.0"), q_order - new_filled)

        # Calculate new weighted average fill price
        curr_avg_p = to_decimal(order.average_fill_price)
        if new_filled > Decimal("0.0"):
            new_avg_p = ((curr_filled * curr_avg_p) + (fill_qty * fill_price)) / new_filled
        else:
            new_avg_p = fill_price

        order.filled_quantity = float(new_filled)
        order.remaining_quantity = float(new_remaining)
        order.average_fill_price = float(new_avg_p)
        order.updated_at = datetime.now(timezone.utc)

        # Transition status
        if new_remaining <= Decimal("1e-9"):
            order.remaining_quantity = 0.0
            order.status = OrderState.FILLED
        else:
            order.status = OrderState.PARTIALLY_FILLED

        return order.status
