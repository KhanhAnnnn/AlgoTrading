"""
libs/bot/adapters.py — Simulation Broker & Redpanda Streaming Adapters (GĐ29)
Provides fail-closed simulated execution, position sizing, and Redpanda ingestion.
Never touches Alpaca Paper write endpoints or live trading systems.
"""

from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timezone
import uuid
import logging
import math

from libs.bot.config import TradingConfig
from libs.bot.domain import (
    MarketDataEvent,
    StrategySignal,
    SignalDecision,
    SimulationOrderIntent,
    SimulatedOrder,
    SimulatedFill,
    SimulatedPosition,
    PortfolioSnapshot,
    BotAuditEvent,
)
from libs.bot.interfaces import (
    SimulationOrderManager,
    BotPortfolioManager,
    BotDataManager,
)
from libs.alpaca_paper_gate import LiveTradingProhibitedError

logger = logging.getLogger("bot-adapters")


class BotSimulationBrokerAdapter(SimulationOrderManager, BotPortfolioManager):
    """
    Simulated Broker and Portfolio Engine for V2 Paper Trading Bot.
    Runs entirely in an isolated sandbox with zero Alpaca Paper mutations.
    Enforces risk rules (e.g. 2% max portfolio risk per trade) and buying power limits.
    """

    def __init__(self, config: Optional[TradingConfig] = None):
        self.config = config or TradingConfig()
        self.session_id = f"sess_{uuid.uuid4().hex[:10]}"
        self.cash: float = self.config.initial_cash
        self.positions: Dict[str, SimulatedPosition] = {}
        self.orders: Dict[str, SimulatedOrder] = {}
        self.fills: List[SimulatedFill] = []
        self.audit_events: List[BotAuditEvent] = []
        self.processed_intents: Dict[str, SimulatedOrder] = {}

        # Fail-closed safety assertion
        if self.config.environment != "SIMULATION":
            raise LiveTradingProhibitedError("BotSimulationBrokerAdapter requires environment='SIMULATION'.")

    def _record_audit(self, event_type: str, reason: str, payload: Dict[str, Any]) -> None:
        event = BotAuditEvent(
            event_id=f"aud_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc),
            component="SIMULATION_BROKER_ADAPTER",
            event_type=event_type,
            trace_id=f"trace_{uuid.uuid4().hex[:8]}",
            reason=reason,
            payload=payload,
            environment="SIMULATION",
        )
        self.audit_events.append(event)

    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        stop_loss_price: Optional[float] = None,
    ) -> float:
        """
        Calculates position size using the 2% risk rule:
        RiskCapital = Equity * risk_per_trade_pct
        If stop loss provided: Qty = RiskCapital / |Price - StopLossPrice|
        Else: Qty = RiskCapital / Price
        """
        snapshot = self.get_portfolio_snapshot()
        equity = snapshot.equity
        risk_capital = equity * self.config.risk_per_trade_pct

        if price <= 0:
            return 0.0

        if stop_loss_price is not None and stop_loss_price > 0 and stop_loss_price != price:
            per_share_risk = abs(price - stop_loss_price)
            qty = risk_capital / per_share_risk
        else:
            qty = risk_capital / price

        # Cap by available buying power (cash)
        max_possible_qty = self.cash / price
        final_qty = min(qty, max_possible_qty)

        # Rounding logic (crypto allows fractional, stocks integer or fractional)
        if "BTC" in symbol or "ETH" in symbol:
            return max(0.0001, round(final_qty, 4))
        return max(1.0, math.floor(final_qty)) if final_qty >= 1.0 else 0.0

    def evaluate_signal(self, signal: StrategySignal, current_price: float) -> SignalDecision:
        """Evaluates whether to accept or reject a strategy signal based on risk boundaries."""
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"

        if signal.signal_type == "HOLD":
            return SignalDecision(
                decision_id=decision_id,
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                status="REJECTED",
                rejection_reason="HOLD_SIGNAL_NOT_ACTIONABLE",
                calculated_qty=0.0,
                environment="SIMULATION",
            )

        if signal.signal_type == "SELL":
            pos = self.positions.get(signal.symbol)
            if not pos or pos.qty <= 0:
                return SignalDecision(
                    decision_id=decision_id,
                    signal_id=signal.signal_id,
                    symbol=signal.symbol,
                    status="REJECTED",
                    rejection_reason="NO_EXISTING_POSITION_TO_SELL",
                    calculated_qty=0.0,
                    environment="SIMULATION",
                )
            return SignalDecision(
                decision_id=decision_id,
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                status="ACCEPTED",
                rejection_reason=None,
                calculated_qty=pos.qty,
                environment="SIMULATION",
            )

        if signal.signal_type == "BUY":
            # 1. Check max open positions
            active_positions = [p for p in self.positions.values() if p.qty > 0]
            if len(active_positions) >= self.config.max_open_positions and signal.symbol not in self.positions:
                return SignalDecision(
                    decision_id=decision_id,
                    signal_id=signal.signal_id,
                    symbol=signal.symbol,
                    status="REJECTED",
                    rejection_reason=f"MAX_POSITIONS_REACHED ({self.config.max_open_positions})",
                    calculated_qty=0.0,
                    environment="SIMULATION",
                )

            # 2. Check position sizing and cash
            qty = self.calculate_position_size(signal.symbol, current_price)
            required_cash = qty * current_price

            if qty <= 0 or required_cash > self.cash:
                return SignalDecision(
                    decision_id=decision_id,
                    signal_id=signal.signal_id,
                    symbol=signal.symbol,
                    status="REJECTED",
                    rejection_reason=f"INSUFFICIENT_BUYING_POWER (Required: {required_cash:.2f}, Cash: {self.cash:.2f})",
                    calculated_qty=0.0,
                    environment="SIMULATION",
                )

            return SignalDecision(
                decision_id=decision_id,
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                status="ACCEPTED",
                rejection_reason=None,
                calculated_qty=qty,
                environment="SIMULATION",
            )

        return SignalDecision(
            decision_id=decision_id,
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            status="REJECTED",
            rejection_reason="UNKNOWN_SIGNAL_TYPE",
            calculated_qty=0.0,
            environment="SIMULATION",
        )

    def submit_order_intent(self, intent: SimulationOrderIntent) -> SimulatedOrder:
        """Converts intent to SimulatedOrder and simulates fulfillment in the sandbox."""
        if intent.environment != "SIMULATION":
            raise LiveTradingProhibitedError("submit_order_intent requires environment='SIMULATION'.")

        # Idempotency check
        if intent.idempotency_key in self.processed_intents:
            return self.processed_intents[intent.idempotency_key]

        order = SimulatedOrder(
            simulated_order_id=f"sim_ord_{uuid.uuid4().hex[:12]}",
            intent_id=intent.intent_id,
            bot_session_id=self.session_id,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            qty=intent.qty,
            limit_price=intent.limit_price,
            status="NEW",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            environment="SIMULATION",
        )

        fill_price = intent.limit_price or 100.0  # Fallback price if none provided
        total_cost = fill_price * intent.qty

        # Simulate execution
        if intent.side == "BUY":
            if total_cost > self.cash:
                order.status = "REJECTED"
                order.updated_at = datetime.now(timezone.utc)
                self.orders[order.simulated_order_id] = order
                self.processed_intents[intent.idempotency_key] = order
                self._record_audit("ORDER_REJECTED", "Insufficient cash at execution", {"order_id": order.simulated_order_id})
                return order

            self.cash -= total_cost
            if intent.symbol in self.positions:
                pos = self.positions[intent.symbol]
                new_qty = pos.qty + intent.qty
                pos.avg_entry_price = ((pos.qty * pos.avg_entry_price) + total_cost) / new_qty
                pos.qty = new_qty
                pos.recalculate(fill_price)
            else:
                self.positions[intent.symbol] = SimulatedPosition(
                    symbol=intent.symbol,
                    qty=intent.qty,
                    avg_entry_price=fill_price,
                    current_price=fill_price,
                    cost_basis=total_cost,
                    market_value=total_cost,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    updated_at=datetime.now(timezone.utc),
                    environment="SIMULATION",
                )

        elif intent.side == "SELL":
            pos = self.positions.get(intent.symbol)
            if not pos or pos.qty < intent.qty:
                order.status = "REJECTED"
                order.updated_at = datetime.now(timezone.utc)
                self.orders[order.simulated_order_id] = order
                self.processed_intents[intent.idempotency_key] = order
                self._record_audit("ORDER_REJECTED", "Insufficient position to sell", {"order_id": order.simulated_order_id})
                return order

            sell_revenue = intent.qty * fill_price
            realized_pnl = (fill_price - pos.avg_entry_price) * intent.qty
            self.cash += sell_revenue
            pos.qty -= intent.qty
            pos.realized_pnl += realized_pnl
            pos.recalculate(fill_price)

        # Create SimulatedFill
        fill = SimulatedFill(
            simulated_fill_id=f"fill_{uuid.uuid4().hex[:12]}",
            simulated_order_id=order.simulated_order_id,
            symbol=intent.symbol,
            side=intent.side,
            fill_price=fill_price,
            fill_qty=intent.qty,
            fill_time=datetime.now(timezone.utc),
            fee=0.0,
            slippage=0.0,
            assumptions="ZERO_SLIPPAGE_BAR_CLOSE",
            environment="SIMULATION",
        )
        self.fills.append(fill)

        order.status = "FILLED"
        order.updated_at = datetime.now(timezone.utc)
        self.orders[order.simulated_order_id] = order
        self.processed_intents[intent.idempotency_key] = order

        self._record_audit(
            "ORDER_FILLED",
            f"Simulated {intent.side} of {intent.qty} {intent.symbol} @ {fill_price:.2f}",
            {"order_id": order.simulated_order_id, "fill_id": fill.simulated_fill_id},
        )
        return order

    def cancel_order(self, simulated_order_id: str) -> bool:
        if simulated_order_id in self.orders:
            order = self.orders[simulated_order_id]
            if order.status == "NEW":
                order.status = "CANCELED"
                order.updated_at = datetime.now(timezone.utc)
                self._record_audit("ORDER_CANCELED", f"Canceled order {simulated_order_id}", {"order_id": simulated_order_id})
                return True
        return False

    def get_open_orders(self) -> List[SimulatedOrder]:
        return [ord for ord in self.orders.values() if ord.status == "NEW"]

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        total_market_value = sum(p.market_value for p in self.positions.values())
        equity = self.cash + total_market_value
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        realized = sum(p.realized_pnl for p in self.positions.values())

        return PortfolioSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:12]}",
            bot_session_id=self.session_id,
            timestamp=datetime.now(timezone.utc),
            cash=self.cash,
            equity=equity,
            positions=dict(self.positions),
            open_orders_count=len(self.get_open_orders()),
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            environment="SIMULATION",
        )


class BotRedpandaConsumerAdapter(BotDataManager):
    """
    Adapter for consuming 1-minute market data from Redpanda streaming topics.
    Uses dedicated consumer group 'paper-bot-v2-group' to protect V1 offsets.
    Filters provisional bars (is_final=False) so strategy signals are generated only on finalized bars.
    """

    def __init__(self, consumer_group: str = "paper-bot-v2-group", require_final: bool = True):
        self.consumer_group = consumer_group
        self.require_final = require_final
        self.latest_bars: Dict[str, MarketDataEvent] = {}
        self._subscribers: List[Callable[[MarketDataEvent], None]] = []

    def get_latest_bar(self, symbol: str) -> Optional[MarketDataEvent]:
        return self.latest_bars.get(symbol)

    def process_bar(self, bar: MarketDataEvent) -> Optional[MarketDataEvent]:
        """Validates bar finalization and caches latest bar."""
        if self.require_final and not bar.is_final:
            logger.debug(f"Ignoring provisional bar for {bar.symbol}")
            return None

        self.latest_bars[bar.symbol] = bar
        for cb in self._subscribers:
            try:
                cb(bar)
            except Exception as e:
                logger.error(f"Callback error processing bar {bar.symbol}: {e}")
        return bar

    def subscribe(self, symbols: List[str], on_bar_callback: Callable[[MarketDataEvent], None]) -> None:
        self._subscribers.append(on_bar_callback)

    def parse_raw_message(self, topic: str, payload: Dict[str, Any]) -> Optional[MarketDataEvent]:
        """Translates raw Redpanda JSON message into normalized MarketDataEvent."""
        symbol = payload.get("symbol", "UNKNOWN")
        open_val = float(payload.get("open", 0.0))
        high_val = float(payload.get("high", 0.0))
        low_val = float(payload.get("low", 0.0))
        close_val = float(payload.get("close", 0.0))
        volume = float(payload.get("volume", 0.0))
        trade_count = int(payload.get("trade_count", 0))
        vwap = float(payload.get("vwap", 0.0))

        # Check finalization: in crypto-bars-1m, field is explicitly is_final; in stock-prices it's 1m bar
        is_final = bool(payload.get("is_final", True))
        source = str(payload.get("source", payload.get("provider", "REDPANDA")))

        event = MarketDataEvent(
            event_id=f"mde_{uuid.uuid4().hex[:12]}",
            symbol=symbol,
            timeframe="1m",
            open=open_val,
            high=high_val,
            low=low_val,
            close=close_val,
            volume=volume,
            trade_count=trade_count,
            vwap=vwap,
            event_time=datetime.now(timezone.utc),
            ingest_time=datetime.now(timezone.utc),
            bar_revision=int(payload.get("bar_revision", 0)),
            is_final=is_final,
            source=source,
            environment="SIMULATION",
        )
        return self.process_bar(event)
