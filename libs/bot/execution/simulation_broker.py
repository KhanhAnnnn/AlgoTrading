"""
libs/bot/execution/simulation_broker.py — Central Simulation Broker Engine (GĐ33)
Coordinates the Order Manager, Fill Engine, Portfolio Adapter, Ledger, and Stores.
Provides an isolated, broker-free exchange simulation on 1m bars.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging

from libs.bot.domain import (
    SimulationOrderIntent,
    SimulatedOrder,
    SimulatedFill,
    MarketDataEvent,
)
from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.execution.lifecycle import OrderState, OrderLifecycleStateMachine
from libs.bot.execution.slippage import SlippageModel, ZeroSlippageModel
from libs.bot.execution.fees import FeeModel, ZeroFeeModel
from libs.bot.execution.fill_engine import FillEngine
from libs.bot.execution.order_manager import SimulationOrderManager
from libs.bot.execution.portfolio_adapter import PortfolioExecutionAdapter
from libs.bot.execution.ledger import ExecutionLedger, ReconciliationReport
from libs.bot.execution.order_store import OrderStore
from libs.bot.execution.fill_store import FillStore
from libs.bot.portfolio.accounting import to_decimal

logger = logging.getLogger("simulation-broker")


class SimulationBroker:
    """
    Central simulation exchange broker sandbox.
    Transforms intents, evaluates order execution against 1m finalized bars,
    applies fills to the simulation portfolio, and maintains an auditable ledger.
    """

    def __init__(
        self,
        portfolio: SimulationPortfolioManager,
        slippage_model: Optional[SlippageModel] = None,
        fee_model: Optional[FeeModel] = None,
        order_store: Optional[OrderStore] = None,
        fill_store: Optional[FillStore] = None,
        ledger: Optional[ExecutionLedger] = None,
        max_participation_rate: float = 0.10,
    ):
        self.portfolio = portfolio
        self.order_store = order_store or OrderStore()
        self.fill_store = fill_store or FillStore()
        self.ledger = ledger or ExecutionLedger()

        self.slippage_model = slippage_model or ZeroSlippageModel()
        self.fee_model = fee_model or ZeroFeeModel()
        self.fill_engine = FillEngine(
            slippage_model=self.slippage_model,
            fee_model=self.fee_model,
            max_participation_rate=max_participation_rate,
        )

        self.order_manager = SimulationOrderManager(self.order_store)
        self.portfolio_adapter = PortfolioExecutionAdapter(self.portfolio)
        self._fills: List[SimulatedFill] = []

        # Telemetry metrics
        self.telemetry: Dict[str, int] = {
            "orders_created": 0,
            "orders_rejected": 0,
            "orders_working": 0,
            "orders_partially_filled": 0,
            "orders_filled": 0,
            "orders_cancelled": 0,
            "orders_expired": 0,
            "fills_generated": 0,
            "duplicate_intents_blocked": 0,
            "duplicate_fills_prevented": 0,
        }

    def submit_intent(self, intent: SimulationOrderIntent) -> SimulatedOrder:
        """
        Accepts a validated SimulationOrderIntent and creates an active WORKING SimulatedOrder.
        Reserves buying power cash in the simulation portfolio if applicable.
        """
        is_valid, err = self.order_manager.validate_intent(intent)
        if not is_valid:
            self.telemetry["orders_rejected"] += 1
            if "DUPLICATE" in (err or ""):
                self.telemetry["duplicate_intents_blocked"] += 1
            raise ValueError(f"Intent {intent.intent_id} rejected: {err}")

        # Reserve cash in portfolio for BUY intents to guarantee buying power
        if intent.side.upper() == "BUY":
            req_notional = Decimal(str(intent.proposed_quantity)) * Decimal(str(intent.reference_price))
            ok = self.portfolio.reserve_cash(req_notional, reference_id=intent.intent_id)
            if not ok:
                self.telemetry["orders_rejected"] += 1
                raise ValueError(
                    f"Insufficient available cash to reserve {req_notional} USD for intent {intent.intent_id}"
                )

        order = self.order_manager.create_order_from_intent(intent)
        self.telemetry["orders_created"] += 1
        self.telemetry["orders_working"] += 1

        self.ledger.record_event(
            event_type="ORDER_SUBMITTED",
            correlation_id={
                "bot_session_id": order.bot_session_id,
                "intent_id": intent.intent_id,
                "order_id": order.simulated_order_id,
                "portfolio_id": self.portfolio.portfolio_id,
            },
            payload={
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.quantity,
                "order_type": order.order_type,
            },
        )
        return order

    def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str = "MARKET",
        quantity: float = 1.0,
        price: float = 100.0,
    ) -> SimulatedOrder:
        """Convenience method creating and submitting a simulation order intent."""
        import uuid
        intent = SimulationOrderIntent(
            intent_id=f"int_{uuid.uuid4().hex[:8]}",
            bot_session_id=self.portfolio.bot_session_id,
            decision_id=f"dec_{uuid.uuid4().hex[:8]}",
            symbol=symbol,
            side=side,
            order_type=order_type,
            proposed_quantity=quantity,
            reference_price=price,
            limit_price=price if order_type == "LIMIT" else None,
        )
        return self.submit_intent(intent)

    def process_market_bar(self, bar: MarketDataEvent) -> List[SimulatedFill]:
        """Alias for process_bar."""
        return self.process_bar(bar)

    def process_bar(self, bar: MarketDataEvent) -> List[SimulatedFill]:
        """
        Matches all eligible open orders for the symbol against the incoming 1m finalized bar.
        Generates fills, updates order status, and applies fills to the portfolio.
        """
        open_orders = self.order_manager.get_orders_by_symbol(bar.symbol)
        active_orders = [
            o for o in open_orders
            if o.status in {OrderState.WORKING, OrderState.PARTIALLY_FILLED}
        ]

        # Sort deterministically by submitted_at (FIFO priority)
        active_orders.sort(key=lambda x: x.submitted_at or x.created_at)

        new_fills: List[SimulatedFill] = []

        for order in active_orders:
            fill = self.fill_engine.evaluate_order(order, bar)
            if fill is None:
                continue

            fill_qty = to_decimal(fill.fill_qty)
            fill_price = to_decimal(fill.fill_price)

            # 1. Update Order Lifecycle
            prev_status = order.status
            new_status = OrderLifecycleStateMachine.apply_fill_to_order(
                order=order,
                fill_qty=fill_qty,
                fill_price=fill_price,
            )

            if new_status == OrderState.FILLED:
                self.telemetry["orders_filled"] += 1
                if prev_status == OrderState.WORKING:
                    self.telemetry["orders_working"] = max(0, self.telemetry["orders_working"] - 1)
            elif new_status == OrderState.PARTIALLY_FILLED:
                self.telemetry["orders_partially_filled"] += 1

            # 2. Apply to Portfolio Manager
            ref_price = order.metadata.get("reference_price", fill.fill_price)
            applied = self.portfolio_adapter.apply_fill(fill, reference_price=ref_price)
            if not applied:
                self.telemetry["duplicate_fills_prevented"] += 1
                continue

            # 3. Persistence
            self.order_store.save_order(order)
            self.fill_store.save_fill(fill)
            self._fills.append(fill)
            new_fills.append(fill)
            self.telemetry["fills_generated"] += 1

            # 4. Ledger Event
            self.ledger.record_event(
                event_type="FILL_SIMULATED",
                correlation_id={
                    "bot_session_id": order.bot_session_id,
                    "intent_id": order.intent_id,
                    "order_id": order.simulated_order_id,
                    "fill_id": fill.simulated_fill_id,
                    "portfolio_id": self.portfolio.portfolio_id,
                },
                payload={
                    "symbol": fill.symbol,
                    "side": fill.side,
                    "fill_qty": fill.fill_qty,
                    "fill_price": fill.fill_price,
                    "fee": fill.fee,
                    "slippage": fill.slippage,
                    "order_status_after": new_status,
                },
            )

        return new_fills

    def cancel_order(self, order_id: str, reason: str = "USER_REQUESTED") -> bool:
        """
        Cancels an open order and releases any remaining reserved cash in the portfolio.
        """
        order = self.order_manager.get_order(order_id)
        if not order:
            return False

        cancelled = self.order_manager.cancel_order(order_id, reason=reason)
        if cancelled:
            self.telemetry["orders_cancelled"] += 1
            if order.side.upper() == "BUY":
                ref_p = order.metadata.get("reference_price", order.limit_price or 0.0)
                if ref_p > 0:
                    self.portfolio_adapter.release_order_reservation(order, reference_price=ref_p)

            self.ledger.record_event(
                event_type="ORDER_CANCELLED",
                correlation_id={
                    "bot_session_id": order.bot_session_id,
                    "intent_id": order.intent_id,
                    "order_id": order.simulated_order_id,
                    "portfolio_id": self.portfolio.portfolio_id,
                },
                payload={"reason": reason, "remaining_qty": order.remaining_quantity},
            )
            return True
        return False

    def reconcile(self, initial_cash: Optional[Decimal] = None) -> ReconciliationReport:
        """Runs three-way mathematical audit across orders, fills, and portfolio state."""
        all_orders = list(self.order_manager._orders.values())
        return self.ledger.reconcile(
            portfolio=self.portfolio,
            orders=all_orders,
            fills=self._fills,
            initial_cash=initial_cash,
        )
