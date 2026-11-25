"""
libs/bot/portfolio/manager.py — Simulation Portfolio Manager (GĐ32)
Core orchestrator for virtual account capital, positions, cash reservations,
lifecycle state transitions, and snapshot generation.
Implements the BotPortfolioManager interface from GĐ29.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timezone
import uuid
import logging

from libs.bot.interfaces import BotPortfolioManager
from libs.bot.domain import (
    StrategySignal,
    SignalDecision,
    PortfolioSnapshot,
    SimulatedPosition,
    PortfolioTransactionEvent,
    BotAuditEvent,
)
from libs.bot.config import TradingConfig
from libs.bot.portfolio.accounting import (
    to_decimal,
    quantize_currency,
    quantize_qty,
    calculate_portfolio_equity,
    calculate_available_cash,
    validate_price_freshness,
)
from libs.bot.portfolio.positions import PositionBook
from libs.bot.portfolio.snapshot import PortfolioSnapshotManager
from libs.alpaca_paper_gate import LiveTradingProhibitedError

logger = logging.getLogger("simulation-portfolio-manager")


class SimulationPortfolioManager(BotPortfolioManager):
    """
    Manages a virtual trading portfolio for AlgoTrading V2.0 Paper Bot.
    Runs entirely within an isolated sandbox (environment='SIMULATION').
    Strictly isolated from Alpaca Paper Broker and V1 Mock Trading Workbench.
    """

    ALLOWED_STATES = {"INITIALIZED", "ACTIVE", "RESTRICTED", "RISK_LOCKED", "CLOSED"}

    def __init__(
        self,
        portfolio_id: Optional[str] = None,
        bot_session_id: Optional[str] = None,
        initial_cash: Union[float, Decimal] = 100000.0,
        config: Optional[TradingConfig] = None,
    ):
        self.config = config or TradingConfig()
        if self.config.environment != "SIMULATION":
            raise LiveTradingProhibitedError("SimulationPortfolioManager requires environment='SIMULATION'.")

        self.portfolio_id = portfolio_id or f"port_{uuid.uuid4().hex[:10]}"
        self.bot_session_id = bot_session_id or f"sess_{uuid.uuid4().hex[:10]}"
        self.state: str = "ACTIVE"  # Default to ACTIVE upon creation

        self._initial_cash: Decimal = to_decimal(initial_cash)
        self._cash: Decimal = to_decimal(initial_cash)
        self._reserved_cash: Decimal = Decimal("0.0")
        self._realized_pnl: Decimal = Decimal("0.0")
        self._peak_equity: Decimal = self._cash

        self.positions = PositionBook()
        self.snapshots: List[PortfolioSnapshot] = []
        self.transactions: List[PortfolioTransactionEvent] = []
        self.audit_events: List[BotAuditEvent] = []
        self._version: int = 1

        # Record initial funding transaction
        self._record_transaction(
            transaction_type="INITIAL_DEPOSIT",
            amount=self._cash,
            description=f"Initial capital allocation of {self._cash} USD",
        )

    @property
    def initial_cash(self) -> Decimal:
        return self._initial_cash

    @property
    def total_fees(self) -> Decimal:
        import re
        fee_sum = Decimal("0.0")
        for tx in self.transactions:
            m = re.search(r"fee=([0-9.]+)", tx.description)
            if m:
                fee_sum += Decimal(m.group(1))
            elif tx.transaction_type == "FEE":
                fee_sum += Decimal(str(abs(tx.amount)))
        return fee_sum

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def reserved_cash(self) -> Decimal:
        return self._reserved_cash

    @property
    def available_cash(self) -> Decimal:
        return calculate_available_cash(self._cash, self._reserved_cash)

    @property
    def realized_pnl(self) -> Decimal:
        return self._realized_pnl

    @property
    def peak_equity(self) -> Decimal:
        return self._peak_equity

    def get_equity(self) -> Decimal:
        """Calculates current total portfolio equity = Cash + Total Position Market Value."""
        total_mv = self.positions.get_total_market_value()
        current_eq = calculate_portfolio_equity(self._cash, total_mv)
        if current_eq > self._peak_equity:
            self._peak_equity = current_eq
        return current_eq

    def set_state(self, new_state: str, reason: str = "") -> None:
        """
        Transitions portfolio lifecycle state.
        Allowed states: INITIALIZED -> ACTIVE -> RESTRICTED -> RISK_LOCKED -> CLOSED.
        """
        if new_state not in self.ALLOWED_STATES:
            raise ValueError(f"Invalid portfolio state: {new_state}. Allowed: {self.ALLOWED_STATES}")

        if self.state == "CLOSED" and new_state != "CLOSED":
            raise ValueError("Cannot transition out of CLOSED terminal state")

        old_state = self.state
        self.state = new_state
        self._version += 1

        self.audit_events.append(
            BotAuditEvent(
                component="PORTFOLIO_MANAGER",
                event_type="STATE_TRANSITION",
                reason=reason or f"State changed from {old_state} to {new_state}",
                payload={
                    "portfolio_id": self.portfolio_id,
                    "old_state": old_state,
                    "new_state": new_state,
                },
                environment="SIMULATION",
            )
        )
        logger.info(f"Portfolio {self.portfolio_id} transitioned: {old_state} -> {new_state} ({reason})")

    def reserve_cash(self, amount: Union[float, Decimal], reference_id: str) -> bool:
        """
        Reserves cash for a pending order intent.
        Returns True if reservation succeeded, False if insufficient available cash.
        """
        amt = to_decimal(amount)
        if amt <= Decimal("0"):
            return False

        if self.available_cash < amt:
            return False

        self._reserved_cash += amt
        self._record_transaction(
            transaction_type="CASH_RESERVE",
            amount=-amt,
            description=f"Reserved {amt} USD for intent {reference_id}",
            reference_id=reference_id,
        )
        return True

    def release_cash(self, amount: Union[float, Decimal], reference_id: str) -> None:
        """Releases previously reserved cash."""
        amt = to_decimal(amount)
        if amt <= Decimal("0"):
            return

        self._reserved_cash = max(Decimal("0.0"), self._reserved_cash - amt)
        self._record_transaction(
            transaction_type="CASH_RELEASE",
            amount=amt,
            description=f"Released {amt} USD reserved for intent {reference_id}",
            reference_id=reference_id,
        )

    def _record_transaction(
        self,
        transaction_type: str,
        amount: Decimal,
        description: str,
        reference_id: str = "",
    ) -> None:
        tx = PortfolioTransactionEvent(
            transaction_id=f"tx_{uuid.uuid4().hex[:12]}",
            portfolio_id=self.portfolio_id,
            timestamp=datetime.now(timezone.utc),
            transaction_type=transaction_type,
            amount=float(amount),
            cash_after=float(self._cash),
            description=description,
            reference_id=reference_id,
            environment="SIMULATION",
        )
        self.transactions.append(tx)

    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        stop_loss_price: Optional[float] = None,
    ) -> float:
        """
        Calculates position size using the 2% risk rule (or configured risk_per_trade_pct).
        Implements BotPortfolioManager.calculate_position_size.
        """
        if price <= 0:
            return 0.0

        equity = self.get_equity()
        risk_pct = to_decimal(self.config.risk_per_trade_pct)
        risk_budget = equity * risk_pct
        price_dec = to_decimal(price)

        if stop_loss_price is not None and stop_loss_price > 0:
            stop_dec = to_decimal(stop_loss_price)
            stop_distance = abs(price_dec - stop_dec)
            if stop_distance == Decimal("0"):
                return 0.0
            qty = risk_budget / stop_distance
        else:
            qty = risk_budget / price_dec

        # Cap by available buying power
        avail_cash = self.available_cash
        max_cash_qty = avail_cash / price_dec
        final_qty = min(qty, max_cash_qty)

        if final_qty <= Decimal("0"):
            return 0.0

        # Fractional support
        if "BTC" in symbol or "ETH" in symbol or "/" in symbol:
            return float(quantize_qty(final_qty, decimals=4))

        # Stocks: check if fractional or integer
        if final_qty < Decimal("1.0"):
            return float(quantize_qty(final_qty, decimals=4))
        return float(quantize_qty(final_qty, decimals=2))

    def evaluate_signal(self, signal: StrategySignal, current_price: float) -> SignalDecision:
        """
        Evaluates a strategy signal against portfolio risk rules.
        Implements BotPortfolioManager.evaluate_signal.
        Detailed signal evaluation is handled by SignalDecisionEngine.
        """
        # Lazy import to avoid circular dependency
        from libs.bot.risk.decision_engine import SignalDecisionEngine
        from libs.bot.risk.config import RiskConfig

        risk_config = RiskConfig(
            risk_per_trade_pct=self.config.risk_per_trade_pct,
            max_concurrent_positions=self.config.max_open_positions,
        )
        engine = SignalDecisionEngine(self, risk_config)
        decision, _ = engine.evaluate(signal, reference_price=current_price)
        return decision

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Returns the latest point-in-time snapshot with checksum."""
        self.get_equity()  # Refresh peak equity
        snapshot = PortfolioSnapshotManager.create_snapshot(
            portfolio_id=self.portfolio_id,
            bot_session_id=self.bot_session_id,
            state=self.state,
            cash=self._cash,
            reserved_cash=self._reserved_cash,
            positions=self.positions.get_all_positions(),
            realized_pnl=self._realized_pnl,
            peak_equity=self._peak_equity,
            version=self._version,
        )
        snapshot.initial_cash = float(self.initial_cash)
        snapshot.total_fees = float(self.total_fees)
        self.snapshots.append(snapshot)
        return snapshot
