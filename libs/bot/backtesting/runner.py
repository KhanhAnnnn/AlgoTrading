"""
libs/bot/backtesting/runner.py — Backtest Runner & Execution Engine (GĐ36)
Coordinates the end-to-end historical backtesting process:
- Deterministic dataset ordering and validation
- Strict warmup phase with indicator initialization and ZERO trading
- Tradable phase with next-bar broker matching, mark-to-market portfolio accounting,
  strategy signal evaluation, and risk-checked order submission
- Comprehensive performance and risk metrics calculation
- Immutable deterministic fingerprint generation and isolated persistence
"""

from typing import List, Dict, Any, Optional, Callable, Union
from datetime import datetime, timezone
from decimal import Decimal
import uuid
import logging

from libs.alpaca_paper_gate import paper_gate, LiveTradingProhibitedError
from libs.bot.domain import MarketDataEvent, SimulatedOrder, SimulatedFill
from libs.bot.portfolio.manager import SimulationPortfolioManager
from libs.bot.portfolio.accounting import to_decimal
from libs.bot.risk.config import RiskConfig
from libs.bot.risk.decision_engine import SignalDecisionEngine
from libs.bot.strategy_engine import StrategyExecutionEngine
from libs.bot.strategies.base import BaseStrategy
from libs.bot.strategies.ma_crossover import MovingAverageCrossoverStrategy
from libs.bot.strategies.rsi_strategy import RSIStrategy
from libs.bot.execution.simulation_broker import SimulationBroker
from libs.bot.execution.slippage import (
    SlippageModel,
    ZeroSlippageModel,
    FixedBpsSlippageModel,
    ConfigurableImpactSlippageModel,
)
from libs.bot.execution.fees import (
    FeeModel,
    ZeroFeeModel,
    ConfigurableFeeModel,
)

from libs.bot.backtesting.config import BacktestConfig
from libs.bot.backtesting.dataset import DatasetManifest, HistoricalDatasetManager
from libs.bot.backtesting.replay_clock import ReplayClock
from libs.bot.backtesting.replay_controller import ReplayController, ReplayMode, ReplayState
from libs.bot.backtesting.metrics import BacktestMetricsCalculator
from libs.bot.backtesting.results import BacktestResult
from libs.bot.backtesting.store import BacktestStore
from libs.bot.backtesting.trade_ledger import (
    serialize_candles,
    compute_strategy_indicators,
    build_closed_trades_and_associations,
    _to_utc_epoch,
)

logger = logging.getLogger("backtest-runner")


class BacktestRunner:
    """
    Executes a quantitative strategy backtest on historical market data
    using AlgoTrading V2.0 simulation components in a strictly isolated environment.
    """

    def __init__(
        self,
        config: BacktestConfig,
        strategy: Optional[BaseStrategy] = None,
        dataset_manager: Optional[HistoricalDatasetManager] = None,
        store: Optional[BacktestStore] = None,
    ):
        self.config = config
        self.config.validate()
        self.custom_strategy = strategy
        self.dataset_manager = dataset_manager or HistoricalDatasetManager()
        self.store = store or BacktestStore()

        self.run_id: str = config.backtest_run_id or f"bt_{uuid.uuid4().hex[:12]}"
        self.clock = ReplayClock()
        self.controller: Optional[ReplayController] = None

        # Isolated component placeholders
        self.portfolio: Optional[SimulationPortfolioManager] = None
        self.broker: Optional[SimulationBroker] = None
        self.decision_engine: Optional[SignalDecisionEngine] = None
        self.strategy_engine: Optional[StrategyExecutionEngine] = None
        self.fee_model: Optional[FeeModel] = None
        self.slippage_model: Optional[SlippageModel] = None

        self._is_setup: bool = False

    def setup(self) -> None:
        """
        Initializes isolated sandbox components for this backtest run.
        Enforces safety invariants: SIMULATION environment and closed execution gates.
        """
        # Safety Gate Verification
        if paper_gate.is_gate_open:
            raise LiveTradingProhibitedError("Backtest execution aborted: PaperExecutionGate is open!")

        # 1. Isolated Portfolio
        self.portfolio = SimulationPortfolioManager(
            portfolio_id=f"port_{self.run_id}",
            bot_session_id=self.run_id,
            initial_cash=self.config.initial_simulated_cash,
        )

        # 2. Fee Model
        if self.config.fee_model == "ZERO":
            self.fee_model = ZeroFeeModel()
        else:
            stocks_per_share = float(self.config.execution_config.get("stocks_per_share", 0.005))
            stocks_min_commission = float(self.config.execution_config.get("stocks_min_commission", 1.0))
            crypto_bps = float(self.config.execution_config.get("crypto_bps", 10.0))
            self.fee_model = ConfigurableFeeModel(
                stocks_per_share=stocks_per_share,
                stocks_min_commission=stocks_min_commission,
                crypto_bps=crypto_bps,
            )

        # 3. Slippage Model
        if self.config.slippage_model == "ZERO":
            self.slippage_model = ZeroSlippageModel()
        elif self.config.slippage_model == "IMPACT":
            spread = float(self.config.execution_config.get("slippage_bps", 2.0))
            self.slippage_model = ConfigurableImpactSlippageModel(
                base_bps=spread,
                impact_coefficient=0.1,
            )
        else:
            spread = float(self.config.execution_config.get("slippage_bps", 5.0))
            self.slippage_model = FixedBpsSlippageModel(bps=spread)

        # 4. Simulation Broker
        self.broker = SimulationBroker(
            portfolio=self.portfolio,
            fee_model=self.fee_model,
            slippage_model=self.slippage_model,
            max_participation_rate=self.config.volume_participation_rate,
        )

        # 5. Risk & Decision Engine
        risk_cfg = self.config.risk_config or RiskConfig(
            max_position_size=Decimal("10000000.0"),
            max_order_size=Decimal("5000000.0"),
            max_drawdown_limit=Decimal("0.99"),
            min_cash_reserve=Decimal("0.0"),
            environment="SIMULATION",
        )
        self.decision_engine = SignalDecisionEngine(
            portfolio=self.portfolio,
            config=risk_cfg,
        )

        # 6. Strategy Engine & Strategy Instance
        self.strategy_engine = StrategyExecutionEngine()
        strategy_to_register = self._create_or_get_strategy()
        self.strategy_engine.add_strategy_instance(strategy_to_register, symbols=self.config.symbols)

        self._is_setup = True
        logger.info(f"BacktestRunner initialized for run_id={self.run_id}")

    def _create_or_get_strategy(self) -> BaseStrategy:
        """Instantiates the strategy based on config or returns the injected custom strategy."""
        if self.custom_strategy is not None:
            return self.custom_strategy

        strat_id = self.config.strategy_id.upper()
        params = self.config.execution_config.get("strategy_params", {})

        if "RSI" in strat_id:
            period = int(params.get("period", 14))
            oversold = float(params.get("oversold", 30.0))
            overbought = float(params.get("overbought", 70.0))
            return RSIStrategy(
                period=period,
                oversold=oversold,
                overbought=overbought,
                strategy_id=self.config.strategy_id,
            )
        else:
            # Default to MA Crossover
            fast = int(params.get("fast_period", params.get("short_window", 20)))
            slow = int(params.get("slow_period", params.get("long_window", 50)))
            return MovingAverageCrossoverStrategy(
                fast_period=fast,
                slow_period=slow,
                strategy_id=self.config.strategy_id,
            )

    def run(
        self,
        bars: Optional[List[MarketDataEvent]] = None,
        dataset_manifest: Optional[DatasetManifest] = None,
        on_bar_callback: Optional[Callable[[MarketDataEvent, Decimal], None]] = None,
    ) -> BacktestResult:
        """
        Executes the backtest synchronously across the provided or loaded dataset.
        Enforces:
        - Deterministic bar sorting
        - Zero trading during warmup phase
        - Next-bar execution parity with Simulation Broker
        - Comprehensive metrics and fingerprint computation
        """
        if not self._is_setup:
            self.setup()

        started_at = datetime.now(timezone.utc)

        # 1. Dataset Resolution & Validation
        if bars is None:
            if dataset_manifest is None:
                raise ValueError("Either 'bars' or 'dataset_manifest' must be provided to run()")
            bars = self.dataset_manager.load_dataset(dataset_manifest.dataset_id)

        if not bars:
            raise ValueError("Cannot run backtest on empty market data bars list")

        # Sort deterministically: (event_time, symbol.upper(), bar_revision)
        sorted_bars = ReplayClock.sort_bars_deterministically(bars)

        # Filter by start_time and end_time if provided
        if self.config.start_time or self.config.end_time:
            filtered = []
            start_bound = self.config.start_time
            end_bound = self.config.end_time
            if start_bound and start_bound.tzinfo is None:
                start_bound = start_bound.replace(tzinfo=timezone.utc)
            if end_bound and end_bound.tzinfo is None:
                end_bound = end_bound.replace(tzinfo=timezone.utc)
            for b in sorted_bars:
                ev_t = b.event_time if b.event_time.tzinfo is not None else b.event_time.replace(tzinfo=timezone.utc)
                if start_bound and ev_t < start_bound:
                    continue
                if end_bound and ev_t > end_bound:
                    continue
                filtered.append(b)
            if filtered:
                sorted_bars = filtered

        # Enforce market_session_policy (STRICT_HOURS restricts equities to 09:30-16:00 ET regular trading hours)
        if self.config.market_session_policy == "STRICT_HOURS":
            rth_bars = []
            for b in sorted_bars:
                inferred_ac = "CRYPTO" if "/" in b.symbol else "STOCKS"
                ac = self.config.asset_classes.get(b.symbol) or getattr(b, "asset_class", None) or inferred_ac
                if HistoricalDatasetManager.is_regular_trading_hours(b.event_time, ac):
                    rth_bars.append(b)
            if not rth_bars:
                raise ValueError(
                    "No regular trading hours (09:30-16:00 America/New_York) bars found in the selected window "
                    "for market_session_policy='STRICT_HOURS'. Switch to 'ALL_HOURS' or expand the date range."
                )
            if len(rth_bars) < len(sorted_bars):
                logger.info(
                    f"STRICT_HOURS policy: filtered {len(sorted_bars) - len(rth_bars)} extended-hours bars "
                    f"({len(rth_bars)} RTH bars retained)."
                )
            sorted_bars = rth_bars

        # Initialize replay controller with resolved bars
        self.controller = ReplayController(bars=sorted_bars, mode=ReplayMode.FAST_REPLAY)

        # Check warmup history sufficiency
        warmup_count = self.config.warmup_bars_count
        if len(sorted_bars) < warmup_count:
            if self.config.warmup_policy == "REQUIRED":
                raise ValueError(
                    f"Insufficient bars ({len(sorted_bars)}) for required warmup ({warmup_count})"
                )
            else:
                warmup_count = min(warmup_count, len(sorted_bars) // 2)

        # Safety Check: All bars must be SIMULATION
        for b in sorted_bars:
            if b.environment != "SIMULATION":
                raise LiveTradingProhibitedError(
                    f"Bar {b.bar_key} environment is '{b.environment}', must be 'SIMULATION'"
                )

        # Split Warmup vs Tradable
        warmup_bars = sorted_bars[:warmup_count]
        tradable_bars = sorted_bars[warmup_count:]

        # Create or update dataset manifest if none provided
        if dataset_manifest is None:
            _, dataset_manifest = self.dataset_manager.create_dataset_from_bars(
                dataset_id=f"auto_ds_{self.run_id}",
                bars=sorted_bars,
                asset_classes=self.config.asset_classes,
            )

        # 2. Warmup Phase (STRICTLY ZERO TRADING)
        logger.info(f"Starting warmup phase with {len(warmup_bars)} bars")
        for w_bar in warmup_bars:
            self.clock.advance_to(w_bar.event_time)
            # Only process bar in strategy engine to warm up indicators
            # Strictly do not pass signals to decision engine or broker!
            self.strategy_engine.process_bar(w_bar)

        # 3. Tradable Phase (Live Replay & Simulation Matching)
        logger.info(f"Starting tradable phase with {len(tradable_bars)} bars")
        equity_curve: List[Dict[str, Any]] = []
        signals_recorded: List[Dict[str, Any]] = []
        decisions_recorded: List[Dict[str, Any]] = []

        initial_time = tradable_bars[0].event_time if tradable_bars else sorted_bars[0].event_time
        equity_curve.append({
            "timestamp": initial_time.isoformat(),
            "equity": float(self.portfolio.get_equity()),
            "cash": float(self.portfolio.cash),
            "unrealized_pnl": 0.0,
            "has_position": False,
        })

        signals_received = 0
        signals_accepted = 0
        signals_rejected = 0

        for bar in tradable_bars:
            # Advance replay clock
            self.clock.advance_to(bar.event_time)

            # Step A: Broker fills pending orders using current bar prices
            self.broker.process_bar(bar)

            # Step B: Mark-to-market position valuation update
            self.portfolio.positions.update_valuation(bar.symbol, to_decimal(bar.close))

            # Step C: Strategy evaluation generates analytical signals on current bar
            raw_signals = self.strategy_engine.process_bar(bar)
            signals = raw_signals if isinstance(raw_signals, list) else ([raw_signals] if raw_signals else [])

            # Step D: Risk & Decision Engine checks signals and submits approved intents to broker
            for sig in signals:
                if sig and sig.signal_type in {"BUY", "SELL"}:
                    signals_received += 1
                    decision, intent = self.decision_engine.evaluate(
                        signal=sig,
                        reference_price=bar.close,
                        source_bar=bar,
                    )
                    sig_time_utc = (
                        bar.event_time
                        if bar.event_time.tzinfo is not None
                        else bar.event_time.replace(tzinfo=timezone.utc)
                    ).astimezone(timezone.utc)
                    signals_recorded.append({
                        "signal_id": sig.signal_id,
                        "strategy_id": sig.strategy_id,
                        "strategy_version": sig.strategy_version,
                        "symbol": sig.symbol,
                        "signal_type": sig.signal_type,
                        "strength": float(sig.strength),
                        "price": float(sig.price),
                        "reason": sig.reason,
                        "reason_codes": list(sig.reason_codes or []),
                        "indicator_values": dict(sig.indicator_values or {}),
                        "source_bar_key": sig.source_bar_key or bar.bar_key,
                        "decision_id": decision.decision_id,
                        "decision_status": decision.status,
                        "timestamp": sig_time_utc.isoformat(),
                        "time": int(sig_time_utc.timestamp()),
                    })
                    decisions_recorded.append({
                        "decision_id": decision.decision_id,
                        "signal_id": sig.signal_id,
                        "status": decision.status,
                        "rejection_reason": decision.rejection_reason,
                    })

                    if decision.status == "ACCEPTED" and intent:
                        signals_accepted += 1
                        try:
                            submitted_order = self.broker.submit_intent(intent)
                            submitted_order.source_bar_key = sig.source_bar_key or bar.bar_key
                            submitted_order.strategy_id = sig.strategy_id
                            submitted_order.strategy_version = sig.strategy_version
                            submitted_order.metadata["signal_id"] = sig.signal_id
                            submitted_order.metadata["strategy_reason"] = sig.reason
                            submitted_order.metadata["reason_codes"] = list(sig.reason_codes or [])
                        except Exception as e:
                            logger.error(f"Broker rejected intent {intent.intent_id}: {e}")
                    else:
                        signals_rejected += 1

            # Step E: Record equity curve point
            current_eq = self.portfolio.get_equity()
            unrealized = self.portfolio.positions.get_total_unrealized_pnl()
            has_pos = self.portfolio.positions.has_position(bar.symbol)
            equity_curve.append({
                "timestamp": bar.event_time.isoformat(),
                "equity": float(current_eq),
                "cash": float(self.portfolio.cash),
                "unrealized_pnl": float(unrealized),
                "has_position": has_pos,
            })

            if on_bar_callback:
                on_bar_callback(bar, current_eq)

        completed_at = datetime.now(timezone.utc)

        # 4. Serialize Executed Orders, Fills, Transactions & Positions
        raw_orders: List[SimulatedOrder] = list(self.broker.order_manager._orders.values())
        raw_fills: List[SimulatedFill] = list(self.broker._fills)
        orders_by_id: Dict[str, SimulatedOrder] = {o.simulated_order_id: o for o in raw_orders}
        signals_by_id: Dict[str, Dict[str, Any]] = {s["signal_id"]: s for s in signals_recorded}

        orders_serialized: List[Dict[str, Any]] = [
            {
                "simulated_order_id": o.simulated_order_id,
                "intent_id": o.intent_id,
                "signal_id": o.metadata.get("signal_id", ""),
                "strategy_id": o.strategy_id or self.config.strategy_id,
                "strategy_reason": o.metadata.get("strategy_reason", ""),
                "reason_codes": list(o.metadata.get("reason_codes", [])),
                "source_bar_key": o.source_bar_key,
                "bot_session_id": o.bot_session_id,
                "symbol": o.symbol,
                "side": o.side,
                "order_type": o.order_type,
                "quantity": float(o.quantity),
                "filled_quantity": float(o.filled_quantity),
                "remaining_quantity": float(o.remaining_quantity),
                "average_fill_price": float(o.average_fill_price) if o.average_fill_price else None,
                "status": o.status,
                "limit_price": float(o.limit_price) if o.limit_price else None,
                "stop_price": float(o.stop_price) if o.stop_price else None,
                "submitted_at": o.submitted_at.isoformat() if getattr(o, "submitted_at", None) else None,
                "updated_at": o.updated_at.isoformat() if getattr(o, "updated_at", None) else None,
                "rejection_reason": o.rejection_reason,
                "environment": o.environment,
            }
            for o in raw_orders
        ]

        fills_serialized: List[Dict[str, Any]] = []
        for f in raw_fills:
            parent_order = orders_by_id.get(f.simulated_order_id)
            sig_id = parent_order.metadata.get("signal_id", "") if parent_order else ""
            sig_info = signals_by_id.get(sig_id, {})
            strat_reason = (
                (parent_order.metadata.get("strategy_reason") if parent_order else None)
                or sig_info.get("reason", "")
            )
            reason_codes = (
                (parent_order.metadata.get("reason_codes") if parent_order else None)
                or sig_info.get("reason_codes", [])
            )
            is_partial = bool(
                parent_order
                and (
                    parent_order.status == "PARTIALLY_FILLED"
                    or float(f.fill_qty) < float(parent_order.quantity) - 1e-6
                )
            )
            fill_iso = f.fill_time.isoformat() if isinstance(f.fill_time, datetime) else str(f.fill_time)
            fills_serialized.append({
                "simulated_fill_id": f.simulated_fill_id,
                "simulated_order_id": f.simulated_order_id,
                "intent_id": f.intent_id or (parent_order.intent_id if parent_order else ""),
                "signal_id": sig_id,
                "strategy_id": (parent_order.strategy_id if parent_order and parent_order.strategy_id else self.config.strategy_id),
                "strategy_reason": strat_reason,
                "reason_codes": list(reason_codes or []),
                "order_type": parent_order.order_type if parent_order else "MARKET",
                "order_status": parent_order.status if parent_order else "FILLED",
                "is_partial_fill": is_partial,
                "symbol": f.symbol,
                "side": f.side,
                "fill_price": float(f.fill_price),
                "fill_qty": float(f.fill_qty),
                "fee": float(f.fee),
                "slippage": float(f.slippage),
                "fill_time": fill_iso,
                "fill_epoch": _to_utc_epoch(f.fill_time),
                "source_bar_key": f.source_bar_key or (parent_order.source_bar_key if parent_order else ""),
                "execution_bar_key": f.execution_bar_key,
                "assumptions": f.assumptions,
                "environment": f.environment,
            })

        transactions_serialized: List[Dict[str, Any]] = [
            {
                "transaction_id": tx.transaction_id,
                "portfolio_id": tx.portfolio_id,
                "timestamp": tx.timestamp.isoformat() if isinstance(tx.timestamp, datetime) else str(tx.timestamp),
                "transaction_type": tx.transaction_type,
                "amount": float(tx.amount),
                "cash_after": float(tx.cash_after),
                "description": tx.description,
                "reference_id": tx.reference_id,
                "environment": tx.environment,
            }
            for tx in self.portfolio.transactions
        ]

        candles_serialized = serialize_candles(
            sorted_bars,
            warmup_count=warmup_count,
            asset_classes=self.config.asset_classes,
        )
        indicators_serialized = compute_strategy_indicators(
            bars=sorted_bars,
            strategy_id=self.config.strategy_id,
            execution_config=self.config.execution_config,
        )
        closed_trades_serialized = build_closed_trades_and_associations(
            fills=fills_serialized,
            signals_by_id=signals_by_id,
        )
        detected_gaps = self.dataset_manager.detect_gaps(
            sorted_bars,
            asset_classes=self.config.asset_classes,
        )

        positions_serialized: List[Dict[str, Any]] = [
            {
                "symbol": pos.symbol,
                "qty": float(pos.qty),
                "cost_basis": float(pos.cost_basis),
                "market_value": float(pos.market_value),
                "unrealized_pnl": float(pos.unrealized_pnl),
                "realized_pnl": float(pos.realized_pnl),
            }
            for pos in (
                self.portfolio.positions.get_all_positions().values()
                if hasattr(self.portfolio.positions.get_all_positions(), "values")
                else self.portfolio.positions.get_all_positions()
            )
        ]

        # 5. Calculate Quantitative Metrics
        total_fees = sum(float(f.fee) for f in raw_fills)
        total_slippage = sum(float(f.slippage) for f in raw_fills)
        primary_asset_class = (
            self.config.asset_classes.get(self.config.symbols[0], "STOCKS")
            if self.config.symbols
            else "STOCKS"
        )

        metrics = BacktestMetricsCalculator.calculate_metrics(
            initial_equity=float(self.config.initial_simulated_cash),
            final_equity=float(self.portfolio.get_equity()),
            realized_pnl=float(self.portfolio.realized_pnl),
            unrealized_pnl=float(self.portfolio.positions.get_total_unrealized_pnl()),
            total_fees=total_fees,
            total_slippage=total_slippage,
            orders=raw_orders,
            fills=raw_fills,
            equity_curve=equity_curve,
            signals_received=signals_received,
            signals_accepted=signals_accepted,
            signals_rejected=signals_rejected,
            asset_class=primary_asset_class,
        )

        # 6. Build BacktestResult
        result = BacktestResult(
            run_id=self.run_id,
            config=self.config,
            metrics=metrics,
            equity_curve=equity_curve,
            drawdown_curve=[],
            orders=orders_serialized,
            fills=fills_serialized,
            signals=signals_recorded,
            decisions=decisions_recorded,
            positions=positions_serialized,
            bars=candles_serialized,
            indicators=indicators_serialized,
            portfolio_transactions=transactions_serialized,
            closed_trades=closed_trades_serialized,
            gaps=detected_gaps,
            manifest=dataset_manifest,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            environment="SIMULATION",
        )

        # 7. Persist to Isolated Backtest Store
        self.store.save(result)
        logger.info(
            f"Backtest {self.run_id} completed successfully. "
            f"Net Return: {metrics['net_return_pct']:.2f}%, "
            f"Total Trades: {metrics['total_trades']}, "
            f"Fingerprint: {result.compute_deterministic_fingerprint()[:16]}..."
        )

        return result
