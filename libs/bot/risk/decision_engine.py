"""
libs/bot/risk/decision_engine.py — Signal Decision Engine & Intent Emitter (GĐ32)
Performs multi-layered verification of StrategySignals against Portfolio state and Risk limits.
Emits SignalDecision and SimulationOrderIntent without creating SimulatedOrders or executing broker fills.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple, Union, Set
from datetime import datetime, timezone
import hashlib
import uuid
import logging

from libs.bot.domain import (
    StrategySignal,
    SignalDecision,
    SimulationOrderIntent,
    MarketDataEvent,
)
from libs.bot.risk.config import RiskConfig
from libs.bot.risk.sizing import PositionSizingEngine, SizingResult
from libs.bot.risk.limits import RiskLimitsEngine
from libs.bot.risk.drawdown import DrawdownMonitor
from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.portfolio.accounting import to_decimal, validate_price_freshness

logger = logging.getLogger("signal-decision-engine")


class SignalDecisionEngine:
    """
    Coordinates end-to-end evaluation of StrategySignals.
    Produces SignalDecision and (if accepted) SimulationOrderIntent.
    Strictly fail-closed and bounded to environment='SIMULATION'.
    """

    def __init__(
        self,
        portfolio: Optional[SimulationPortfolioManager] = None,
        config: Optional[RiskConfig] = None,
    ):
        self.portfolio = portfolio or SimulationPortfolioManager()
        self.config = config or RiskConfig()
        self.sizing_engine = PositionSizingEngine(self.config)
        self.limits_engine = RiskLimitsEngine(self.config)
        self.drawdown_monitor = DrawdownMonitor(
            portfolio_id=self.portfolio.portfolio_id,
            initial_equity=self.portfolio.get_equity(),
            max_drawdown_pct=to_decimal(self.config.max_drawdown_pct),
        )

        self._seen_signal_ids: Set[str] = set()
        self._emitted_intents: Dict[str, SimulationOrderIntent] = {}

        # Telemetry metrics
        self.telemetry: Dict[str, int] = {
            "signals_received": 0,
            "decisions_accepted": 0,
            "decisions_rejected": 0,
            "decisions_deferred": 0,
            "intents_created": 0,
            "duplicate_signals": 0,
            "risk_limit_breaches": 0,
            "sizing_validation_errors": 0,
            "stale_price_rejections": 0,
        }

    def evaluate(
        self,
        signal: StrategySignal,
        reference_price: Union[float, Decimal],
        stop_loss_price: Optional[Union[float, Decimal]] = None,
        source_bar: Optional[MarketDataEvent] = None,
        price_time: Optional[datetime] = None,
        quantity_precision: Optional[int] = None,
    ) -> Tuple[SignalDecision, Optional[SimulationOrderIntent]]:
        """
        Executes full 10-step verification pipeline on an incoming StrategySignal.
        Returns (SignalDecision, Optional[SimulationOrderIntent]).
        """
        self.telemetry["signals_received"] += 1
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        rejection_codes: List[str] = []

        # 1. Environment Guard
        if signal.environment != "SIMULATION":
            self.telemetry["decisions_rejected"] += 1
            rejection_codes.append("NON_SIMULATION_ENVIRONMENT")
            return self._build_decision(
                decision_id=decision_id,
                signal=signal,
                status="REJECTED",
                reason_codes=rejection_codes,
            ), None

        # 2. Duplicate Signal Check
        if signal.signal_id in self._seen_signal_ids:
            self.telemetry["duplicate_signals"] += 1
            self.telemetry["decisions_rejected"] += 1
            rejection_codes.append("DUPLICATE_SIGNAL")
            return self._build_decision(
                decision_id=decision_id,
                signal=signal,
                status="REJECTED",
                reason_codes=rejection_codes,
            ), None

        self._seen_signal_ids.add(signal.signal_id)

        # 3. Actionable Signal Type Check
        if signal.signal_type not in {"BUY", "SELL"}:
            self.telemetry["decisions_rejected"] += 1
            rejection_codes.append(f"UNSUPPORTED_SIGNAL_TYPE_{signal.signal_type}")
            return self._build_decision(
                decision_id=decision_id,
                signal=signal,
                status="REJECTED",
                reason_codes=rejection_codes,
            ), None

        # 4. Strategy Version Whitelist Check
        if signal.strategy_version not in self.config.strategy_version_whitelist:
            self.telemetry["decisions_rejected"] += 1
            rejection_codes.append(f"INCOMPATIBLE_STRATEGY_VERSION_{signal.strategy_version}")
            return self._build_decision(
                decision_id=decision_id,
                signal=signal,
                status="REJECTED",
                reason_codes=rejection_codes,
            ), None

        # 5. Source Bar Verification (if provided)
        if source_bar is not None:
            if not source_bar.is_final:
                self.telemetry["decisions_rejected"] += 1
                rejection_codes.append("UNFINALIZED_SOURCE_BAR")
                return self._build_decision(
                    decision_id=decision_id,
                    signal=signal,
                    status="REJECTED",
                    reason_codes=rejection_codes,
                ), None
            if source_bar.bar_revision != signal.source_bar_revision:
                self.telemetry["decisions_rejected"] += 1
                rejection_codes.append("SOURCE_BAR_REVISION_MISMATCH")
                return self._build_decision(
                    decision_id=decision_id,
                    signal=signal,
                    status="REJECTED",
                    reason_codes=rejection_codes,
                ), None

        # 6. Price Freshness & Validity Check
        ref_clock = source_bar.event_time if (source_bar and getattr(source_bar, "event_time", None)) else None
        is_fresh, freshness_err = validate_price_freshness(
            price=reference_price,
            price_time=price_time or signal.signal_time,
            max_age_seconds=self.config.max_price_age_seconds,
            reference_time=ref_clock,
        )
        if not is_fresh:
            if "STALE" in (freshness_err or ""):
                self.telemetry["stale_price_rejections"] += 1
                rejection_codes.append(f"STALE_REFERENCE_PRICE ({freshness_err})")
            else:
                rejection_codes.append(f"INVALID_REFERENCE_PRICE ({freshness_err})")
            self.telemetry["decisions_rejected"] += 1
            return self._build_decision(
                decision_id=decision_id,
                signal=signal,
                status="REJECTED",
                reason_codes=rejection_codes,
            ), None

        ref_p = to_decimal(reference_price)

        # 7. Portfolio State Check
        if self.portfolio.state == "RISK_LOCKED":
            self.telemetry["decisions_rejected"] += 1
            rejection_codes.append("PORTFOLIO_RISK_LOCKED")
            return self._build_decision(
                decision_id=decision_id,
                signal=signal,
                status="REJECTED",
                reason_codes=rejection_codes,
            ), None

        if self.portfolio.state in {"RESTRICTED", "CLOSED"}:
            self.telemetry["decisions_rejected"] += 1
            rejection_codes.append(f"PORTFOLIO_STATE_{self.portfolio.state}")
            return self._build_decision(
                decision_id=decision_id,
                signal=signal,
                status="REJECTED",
                reason_codes=rejection_codes,
            ), None

        # 8. Drawdown Monitor Update & Lockout Check
        curr_equity = self.portfolio.get_equity()
        dd_snap, risk_event = self.drawdown_monitor.update(curr_equity)
        if self.drawdown_monitor.is_locked:
            self.portfolio.set_state("RISK_LOCKED", reason=self.drawdown_monitor.lock_reason or "Drawdown breached")
            self.telemetry["risk_limit_breaches"] += 1
            self.telemetry["decisions_rejected"] += 1
            rejection_codes.append("DRAWDOWN_LIMIT_BREACHED")
            return self._build_decision(
                decision_id=decision_id,
                signal=signal,
                status="REJECTED",
                reason_codes=rejection_codes,
                risk_snapshot={"drawdown_pct": dd_snap.drawdown_pct, "is_locked": True},
            ), None

        # 9. Handle SELL Signal logic
        existing_pos = self.portfolio.positions.get_position(signal.symbol)
        has_pos = existing_pos is not None and abs(existing_pos.qty) > 1e-9

        if signal.signal_type == "SELL":
            if not self.config.allow_short and (not has_pos or existing_pos.qty <= 0):
                self.telemetry["decisions_rejected"] += 1
                rejection_codes.append("NO_EXISTING_POSITION_TO_SELL")
                return self._build_decision(
                    decision_id=decision_id,
                    signal=signal,
                    status="REJECTED",
                    reason_codes=rejection_codes,
                ), None

            sell_qty = to_decimal(existing_pos.qty) if has_pos else to_decimal(self.config.fixed_qty)
            sell_notional = sell_qty * ref_p

            decision = self._build_decision(
                decision_id=decision_id,
                signal=signal,
                status="ACCEPTED",
                reason_codes=["SELL_INTENT_APPROVED"],
                calculated_qty=float(sell_qty),
                sizing_snapshot={"proposed_qty": float(sell_qty), "proposed_notional": float(sell_notional)},
            )
            intent = self._build_intent(
                decision_id=decision_id,
                signal=signal,
                side="SELL",
                proposed_qty=float(sell_qty),
                proposed_notional=float(sell_notional),
                reference_price=float(ref_p),
            )
            self.telemetry["decisions_accepted"] += 1
            self.telemetry["intents_created"] += 1
            return decision, intent

        # 10. Handle BUY Signal logic
        # A. Portfolio Guards
        passed_guards, guard_codes = self.limits_engine.check_portfolio_guards(
            symbol=signal.symbol,
            has_existing_position=has_pos,
            active_positions_count=self.portfolio.positions.get_active_positions_count(),
            is_drawdown_locked=self.drawdown_monitor.is_locked,
            current_drawdown_pct=to_decimal(dd_snap.drawdown_pct),
        )
        if not passed_guards:
            self.telemetry["risk_limit_breaches"] += 1
            self.telemetry["decisions_rejected"] += 1
            return self._build_decision(
                decision_id=decision_id,
                signal=signal,
                status="REJECTED",
                reason_codes=guard_codes,
            ), None

        # B. Position Sizing
        sizing_res = self.sizing_engine.calculate_size(
            symbol=signal.symbol,
            signal=signal,
            reference_price=ref_p,
            equity=curr_equity,
            available_cash=self.portfolio.available_cash,
            stop_loss_price=stop_loss_price,
            price_time=price_time or signal.signal_time,
            reference_time=ref_clock,
            quantity_precision=quantity_precision,
        )
        if not sizing_res.is_valid:
            self.telemetry["sizing_validation_errors"] += 1
            self.telemetry["decisions_rejected"] += 1
            rejection_codes.append(sizing_res.reason_code or "SIZING_VALIDATION_FAILED")
            return self._build_decision(
                decision_id=decision_id,
                signal=signal,
                status="REJECTED",
                reason_codes=rejection_codes,
                rejection_reason=sizing_res.rejection_reason,
                sizing_snapshot=sizing_res.risk_calculation_trace,
            ), None

        # C. Position Limits Evaluation
        passed_pos_limits, pos_limit_codes, pos_metrics = self.limits_engine.check_position_limits(
            symbol=signal.symbol,
            proposed_qty=sizing_res.proposed_quantity,
            proposed_notional=sizing_res.proposed_notional,
            current_pos=existing_pos,
            equity=curr_equity,
            gross_exposure=self.portfolio.positions.get_gross_exposure(),
        )
        if not passed_pos_limits:
            self.telemetry["risk_limit_breaches"] += 1
            self.telemetry["decisions_rejected"] += 1
            return self._build_decision(
                decision_id=decision_id,
                signal=signal,
                status="REJECTED",
                reason_codes=pos_limit_codes,
                risk_snapshot=pos_metrics,
                sizing_snapshot=sizing_res.risk_calculation_trace,
            ), None

        # All 10 checks PASS: Accept signal and emit SimulationOrderIntent
        self.telemetry["decisions_accepted"] += 1
        self.telemetry["intents_created"] += 1

        decision = self._build_decision(
            decision_id=decision_id,
            signal=signal,
            status="ACCEPTED",
            reason_codes=["BUY_INTENT_APPROVED"],
            calculated_qty=float(sizing_res.proposed_quantity),
            risk_snapshot=pos_metrics,
            sizing_snapshot=sizing_res.risk_calculation_trace,
        )
        intent = self._build_intent(
            decision_id=decision_id,
            signal=signal,
            side="BUY",
            proposed_qty=float(sizing_res.proposed_quantity),
            proposed_notional=float(sizing_res.proposed_notional),
            reference_price=float(ref_p),
        )

        return decision, intent

    def evaluate_signal(
        self,
        signal: StrategySignal,
        portfolio: Optional[SimulationPortfolioManager] = None,
        reference_price: Optional[float] = None,
    ) -> SignalDecision:
        if portfolio is not None:
            self.portfolio = portfolio
        price = reference_price or signal.price
        decision, _ = self.evaluate(signal, reference_price=price)
        return decision

    def _build_decision(
        self,
        decision_id: str,
        signal: StrategySignal,
        status: str,
        reason_codes: List[str],
        rejection_reason: Optional[str] = None,
        calculated_qty: float = 0.0,
        risk_snapshot: Optional[Dict[str, Any]] = None,
        sizing_snapshot: Optional[Dict[str, Any]] = None,
    ) -> SignalDecision:
        primary_reason = rejection_reason or (reason_codes[0] if reason_codes else None)
        return SignalDecision(
            decision_id=decision_id,
            signal_id=signal.signal_id,
            portfolio_id=self.portfolio.portfolio_id,
            symbol=signal.symbol,
            status=status,
            rejection_reason=primary_reason if status != "ACCEPTED" else None,
            reason_codes=reason_codes,
            timestamp=datetime.now(timezone.utc),
            evaluated_by="PORTFOLIO_MANAGER",
            calculated_qty=calculated_qty,
            risk_snapshot=risk_snapshot or {},
            sizing_snapshot=sizing_snapshot or {},
            configuration_hash=self.config.compute_hash(),
            trace_id=signal.trace_id or f"trace_{uuid.uuid4().hex[:12]}",
            environment="SIMULATION",
        )

    def _build_intent(
        self,
        decision_id: str,
        signal: StrategySignal,
        side: str,
        proposed_qty: float,
        proposed_notional: float,
        reference_price: float,
    ) -> SimulationOrderIntent:
        idemp_payload = f"{decision_id}:{signal.signal_id}:{signal.symbol}:{side}:{proposed_qty:.4f}"
        idemp_key = hashlib.sha256(idemp_payload.encode("utf-8")).hexdigest()

        intent = SimulationOrderIntent(
            intent_id=f"intent_{uuid.uuid4().hex[:12]}",
            decision_id=decision_id,
            signal_id=signal.signal_id,
            bot_session_id=self.portfolio.bot_session_id,
            portfolio_id=self.portfolio.portfolio_id,
            symbol=signal.symbol,
            side=side,
            order_type="MARKET",
            proposed_quantity=proposed_qty,
            proposed_notional=proposed_notional,
            reference_price=reference_price,
            risk_configuration_version=self.config.risk_configuration_version,
            idempotency_key=idemp_key,
            created_at=datetime.now(timezone.utc),
            environment="SIMULATION",
        )
        self._emitted_intents[intent.intent_id] = intent
        return intent
