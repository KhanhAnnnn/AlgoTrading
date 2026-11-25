"""
libs/bot/reliability/scenarios.py — Standardized Integration & Stress Scenarios (GĐ39)
Contains reproducible scenario drivers for E2E pipeline, multi-bot isolation,
queue overflow remediation, crash recovery, and historical replay cross-check.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
import uuid
import logging

from libs.bot.domain import MarketDataEvent, SimulatedOrder, SimulatedFill
from libs.bot.orchestration.lifecycle import BotLifecycleState, BotLifecycleStateMachine
from libs.bot.multibot.registry import BotDefinition, BotRegistry
from libs.bot.multibot.dispatcher import V2MarketDataDispatcher
from libs.bot.multibot.supervisor import MultiBotSupervisor
from libs.bot.multibot.subscriptions import BotSubscription
from libs.bot.reliability.reconciliation import SimulationReconciliationEngine
from libs.bot.reliability.fault_injection import FaultInjectionEngine, FailurePoint, SimulatedCrashError

logger = logging.getLogger("reliability-scenarios")


class ReliabilityScenarios:
    """
    Pre-packaged scenarios executing standard reliability, isolation, and failure tests.
    """

    @staticmethod
    def create_synthetic_1m_bar(
        symbol: str = "NVDA",
        event_id: Optional[str] = None,
        event_time: Optional[datetime] = None,
        price: float = 100.0,
        volume: int = 1000,
        is_final: bool = True,
    ) -> MarketDataEvent:
        """Helper to manufacture deterministic 1m final market data bars."""
        ev_id = event_id or f"ev_{uuid.uuid4().hex[:8]}"
        ev_time = event_time or datetime.now(timezone.utc)
        return MarketDataEvent(
            event_id=ev_id,
            symbol=symbol,
            timeframe="1m",
            open=price,
            high=price * 1.002,
            low=price * 0.998,
            close=price,
            volume=volume,
            event_time=ev_time,
            is_final=is_final,
            revision=1,
            source="SIMULATED_RELIABILITY_SCENARIO",
        )

    @classmethod
    def run_e2e_causation_scenario(
        cls,
        supervisor: MultiBotSupervisor,
        bot_id: str,
        bars_count: int = 30,
        start_price: float = 100.0,
    ) -> Dict[str, Any]:
        """
        Executes a complete causation pipeline scenario:
        1m Bars -> Signals -> Decisions -> Intents -> Orders -> Next-bar Fills -> Ledger Update.
        """
        runtime = supervisor._active_runtimes.get(bot_id)
        if not runtime:
            raise ValueError(f"Bot '{bot_id}' is not active in supervisor")

        base_time = datetime(2026, 11, 24, 14, 30, tzinfo=timezone.utc)
        events_sent = []
        price = start_price

        for i in range(bars_count):
            # Alternating trend to produce crossovers and signals
            price += 0.50 if i % 4 < 2 else -0.50
            bar = cls.create_synthetic_1m_bar(
                symbol="NVDA",
                event_id=f"e2e_bar_{i+1}",
                event_time=base_time + timedelta(minutes=i),
                price=price,
            )
            supervisor.dispatcher.dispatch_event(bar)
            events_sent.append(bar)

            # Drain and process event in bot orchestrator
            ev = supervisor.dispatcher.get_next_event(bot_id)
            if ev and runtime.state == BotLifecycleState.RUNNING:
                # Orchestrator handles bar
                runtime.orchestrator.on_market_data(ev)

        # Audit portfolio balance post scenario
        fills = getattr(runtime.orchestrator.broker, "_fills", []) or []
        recon = SimulationReconciliationEngine.audit_portfolio(
            portfolio=runtime.orchestrator.portfolio,
            fills=fills,
        )

        return {
            "scenario": "E2E_CAUSATION",
            "bot_id": bot_id,
            "events_dispatched": len(events_sent),
            "reconciliation": recon,
            "portfolio_snapshot": runtime.orchestrator.portfolio.get_portfolio_snapshot(),
        }

    @classmethod
    def run_deterministic_e2e_trading_scenario(
        cls,
        supervisor: MultiBotSupervisor,
        bot_id: str,
        symbol: str = "NVDA",
        initial_cash: float = 100000.0,
    ) -> Dict[str, Any]:
        """
        Executes a deterministic synthetic 1m fixture scenario producing an actual BUY trade:
        Final 1m bars -> MA Bullish Crossover -> SignalDecision ACCEPTED -> SimulationOrderIntent ->
        SimulatedOrder (WORKING) -> Next-bar SimulatedFill with fees & slippage -> Portfolio Position & Cash -> Reconciliation BALANCED.
        """
        runtime = supervisor._active_runtimes.get(bot_id)
        if not runtime:
            raise ValueError(f"Bot '{bot_id}' is not active in supervisor")

        from libs.bot.execution.fees import ConfigurableFeeModel
        from libs.bot.execution.slippage import FixedBpsSlippageModel

        # Configure deterministic fee and slippage models
        runtime.orchestrator.broker.fill_engine.fee_model = ConfigurableFeeModel(stocks_per_share=0.01, stocks_min_commission=1.50)
        runtime.orchestrator.broker.fill_engine.slippage_model = FixedBpsSlippageModel(bps=5.0)

        snap_before = runtime.orchestrator.portfolio.get_portfolio_snapshot()
        base_time = datetime(2026, 11, 24, 8, 0, tzinfo=timezone.utc)

        # Synthetic deterministic price curve: 52 flat warmup bars, 5 drop bars, 5 surge bars (triggering Golden Cross at bar 59), 2 execution bars
        prices = [100.0] * 52 + [95.0, 93.0, 91.0, 89.0, 87.0] + [105.0, 115.0, 125.0, 135.0, 145.0] + [146.0, 147.0]

        events_sent = []
        step_trace = []

        for i, p in enumerate(prices):
            bar_time = base_time + timedelta(minutes=i)
            bar = cls.create_synthetic_1m_bar(
                symbol=symbol,
                price=p,
                event_time=bar_time,
                event_id=f"det_e2e_bar_{i+1}",
                is_final=True,
            )
            supervisor.dispatcher.dispatch_event(bar)
            events_sent.append(bar)

            res = runtime.orchestrator.on_market_data(bar)
            if res and (res.get("signals") or res.get("fills_generated", 0) > 0):
                step_trace.append({"bar_index": i + 1, "bar_time": bar_time.isoformat(), "result": res})

        fills = getattr(runtime.orchestrator.broker, "_fills", []) or []
        orders = list(runtime.orchestrator.broker.order_manager._orders.values())
        snap_after = runtime.orchestrator.portfolio.get_portfolio_snapshot()
        recon = SimulationReconciliationEngine.audit_portfolio(
            portfolio=runtime.orchestrator.portfolio,
            fills=fills,
        )

        return {
            "scenario": "DETERMINISTIC_E2E_TRADING",
            "fixture_type": "SYNTHETIC_DETERMINISTIC_1M_OHLCV",
            "bot_id": bot_id,
            "symbol": symbol,
            "bars_processed": len(events_sent),
            "orders_count": len(orders),
            "fills_count": len(fills),
            "orders": [
                {
                    "order_id": o.simulated_order_id,
                    "side": o.side,
                    "qty": o.quantity,
                    "status": o.status,
                    "source_bar_key": o.source_bar_key,
                }
                for o in orders
            ],
            "fills": [
                {
                    "fill_id": f.fill_id,
                    "order_id": f.order_id,
                    "side": f.side,
                    "qty": float(f.fill_qty),
                    "price": float(f.fill_price),
                    "fee": float(f.fee),
                    "slippage": float(f.slippage),
                }
                for f in fills
            ],
            "portfolio_before": {
                "cash": float(snap_before.cash),
                "positions_count": len(snap_before.positions),
            },
            "portfolio_after": {
                "cash": float(snap_after.cash),
                "positions": {
                    k: {"qty": float(v.qty), "cost_basis": float(v.cost_basis), "market_value": float(v.market_value)}
                    for k, v in snap_after.positions.items()
                },
                "total_fees": float(snap_after.total_fees),
            },
            "reconciliation": {
                "is_balanced": recon.is_balanced,
                "cash_balanced": recon.cash_balanced,
                "positions_balanced": recon.positions_balanced,
                "discrepancies": recon.discrepancies,
                "metrics": recon.metrics,
            },
            "next_bar_execution_verified": len(fills) > 0 and orders[0].source_bar_key != fills[0].source_bar_key,
            "step_trace": step_trace,
            "status": "PASS" if (len(fills) > 0 and recon.is_balanced) else "FAIL",
        }

    @classmethod
    def run_queue_overflow_recovery_scenario(
        cls,
        dispatcher: V2MarketDataDispatcher,
        bot_id: str,
        queue_capacity: int = 5,
        overflow_count: int = 10,
    ) -> Dict[str, Any]:
        """
        Simulates queue capacity overflow -> DATA_GAP_BLOCKED -> Backlog Replay -> Reconciled.
        """
        dispatcher.subscription_manager.register_subscription(
            BotSubscription(bot_id=bot_id, symbols={"NVDA"}, timeframe="1m", is_active=True)
        )

        base_time = datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc)
        dispatched_events = []
        dropped_events = []

        total_bars = queue_capacity + overflow_count
        for i in range(total_bars):
            bar = cls.create_synthetic_1m_bar(
                symbol="NVDA",
                event_id=f"overflow_bar_{i+1}",
                event_time=base_time + timedelta(minutes=i),
            )
            res = dispatcher.dispatch_event(bar)
            status = res.get(bot_id)
            if status == "ENQUEUED":
                dispatched_events.append(bar)
            else:
                dropped_events.append(bar)

        was_blocked = dispatcher.is_bot_blocked(bot_id)

        # Replay missing backlog events
        dispatcher.reconcile_data_gap(bot_id, dropped_events)
        is_blocked_after_reconcile = dispatcher.is_bot_blocked(bot_id)

        return {
            "scenario": "QUEUE_OVERFLOW_RECOVERY",
            "bot_id": bot_id,
            "queue_capacity": queue_capacity,
            "enqueued_count": len(dispatched_events),
            "dropped_count": len(dropped_events),
            "was_blocked": was_blocked,
            "is_blocked_after_reconcile": is_blocked_after_reconcile,
            "recovery_successful": was_blocked and not is_blocked_after_reconcile,
        }
