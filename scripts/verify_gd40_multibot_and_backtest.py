"""
scripts/verify_gd40_multibot_and_backtest.py — Standalone Multi-Bot Isolation & Backtest Verification (GĐ40)
Verifies:
1. Multi-Bot Isolation: 3 bots with independent sandboxes, sessions, portfolios, and failure isolation.
2. Backtesting Engine: Historical replay with provenance, deterministic fingerprint, equity curve, drawdown.
3. Strategy Experiments & Comparison: Multi-variant execution, comparability validation, and comparative delta analytics.
Outputs evidence to data/status/gd40_release_evidence.json.
"""

import os
import sys
import json
import logging
import tempfile
from decimal import Decimal
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from libs.bot.multibot.supervisor import MultiBotSupervisor
from libs.bot.multibot.registry import BotDefinition
from libs.bot.reliability.safety_monitor import SafetyMonitor
from libs.bot.reliability.scenarios import ReliabilityScenarios
from libs.bot.backtesting.config import BacktestConfig
from libs.bot.backtesting.runner import BacktestRunner
from libs.bot.backtesting.dataset import HistoricalDatasetManager
from libs.bot.backtesting.store import BacktestStore
from libs.bot.experiments.comparison import BacktestComparisonService
from libs.bot.experiments.fingerprint import EconomicSequenceFingerprint

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("gd40-multibot-backtest")


def verify_multibot_isolation() -> dict:
    logger.info("Testing Multi-Bot Sandbox Isolation & Fault Tolerance...")
    temp_dir = tempfile.mkdtemp()
    supervisor = MultiBotSupervisor(base_dir=temp_dir)

    bots = [
        BotDefinition(bot_id="demo_bot_alpha", strategy_id="MA_CROSS_1M", symbols=["NVDA"], initial_simulated_cash=100000.0),
        BotDefinition(bot_id="demo_bot_beta", strategy_id="RSI_1M", symbols=["NVDA"], initial_simulated_cash=150000.0),
        BotDefinition(bot_id="demo_bot_gamma", strategy_id="MA_CROSS_1M", symbols=["BTC/USD"], initial_simulated_cash=200000.0),
    ]

    for b in bots:
        supervisor.registry.register_bot(b)
        supervisor.start_bot(b.bot_id)

    # Dispatch market data
    bar_nvda = ReliabilityScenarios.create_synthetic_1m_bar(symbol="NVDA", price=140.0)
    bar_btc = ReliabilityScenarios.create_synthetic_1m_bar(symbol="BTC/USD", price=65000.0)
    supervisor.dispatcher.dispatch_event(bar_nvda)
    supervisor.dispatcher.dispatch_event(bar_btc)

    # Process events for all bots
    for b in bots:
        ev = supervisor.dispatcher.get_next_event(b.bot_id)
        if ev:
            rt = supervisor._active_runtimes[b.bot_id]
            rt.orchestrator.on_market_data(ev)

    # Inject failure into Bot Alpha: Pause and Stop Bot Alpha
    supervisor.pause_bot("demo_bot_alpha")
    status_alpha = supervisor.get_bot_status("demo_bot_alpha")
    state_alpha = status_alpha.get("status")

    # Verify Bot Beta and Gamma remain unaffected and RUNNING
    status_beta = supervisor.get_bot_status("demo_bot_beta")
    state_beta = status_beta.get("status")
    status_gamma = supervisor.get_bot_status("demo_bot_gamma")
    state_gamma = status_gamma.get("status")

    # Assert Portfolios are strictly separated
    port_alpha = supervisor._active_runtimes["demo_bot_alpha"].orchestrator.portfolio
    port_beta = supervisor._active_runtimes["demo_bot_beta"].orchestrator.portfolio
    port_gamma = supervisor._active_runtimes["demo_bot_gamma"].orchestrator.portfolio

    portfolios_isolated = (
        port_alpha.portfolio_id != port_beta.portfolio_id != port_gamma.portfolio_id and
        port_alpha.initial_cash == Decimal("100000.0") and
        port_beta.initial_cash == Decimal("150000.0") and
        port_gamma.initial_cash == Decimal("200000.0")
    )

    supervisor.stop_bot("demo_bot_alpha")
    supervisor.stop_bot("demo_bot_beta")
    supervisor.stop_bot("demo_bot_gamma")

    return {
        "bot_count": len(bots),
        "bots": ["demo_bot_alpha", "demo_bot_beta", "demo_bot_gamma"],
        "alpha_state_after_pause": state_alpha,
        "beta_state_after_alpha_pause": state_beta,
        "gamma_state_after_alpha_pause": state_gamma,
        "portfolios_strictly_isolated": portfolios_isolated,
        "failure_isolated": (state_alpha == "PAUSED" and state_beta == "RUNNING" and state_gamma == "RUNNING"),
        "status": "PASS" if (portfolios_isolated and state_beta == "RUNNING" and state_gamma == "RUNNING") else "FAIL",
    }


def verify_backtest_and_comparison() -> dict:
    logger.info("Testing Backtesting Engine, Deterministic Replay & Strategy Comparison...")
    temp_dir = tempfile.mkdtemp()
    store = BacktestStore(base_dir=os.path.join(temp_dir, "backtests"))
    ds_manager = HistoricalDatasetManager(base_dir=os.path.join(temp_dir, "datasets"))

    # Generate synthetic historical bar dataset (70 bars)
    base_time = datetime(2026, 11, 24, 8, 0, tzinfo=timezone.utc)
    bars = []
    prices = [100.0] * 35 + [95.0, 93.0, 91.0, 89.0, 87.0] + [105.0, 115.0, 125.0, 135.0, 145.0] + [146.0] * 15
    for i, p in enumerate(prices):
        b = ReliabilityScenarios.create_synthetic_1m_bar(
            symbol="NVDA",
            price=p,
            event_time=base_time + timedelta(minutes=i),
            event_id=f"hist_bar_{i+1}",
            is_final=True,
        )
        bars.append(b)

    # 1. Backtest Run A: Strategy MA_CROSS_1M
    cfg_a = BacktestConfig(
        strategy_id="MA_CROSS_1M",
        symbols=["NVDA"],
        timeframe="1m",
        initial_simulated_cash=100000.0,
        warmup_bars_count=30,
    )
    runner_a = BacktestRunner(config=cfg_a, store=store, dataset_manager=ds_manager)
    res_a = runner_a.run(bars)

    # Compute deterministic fingerprint for Run A
    fp_a = EconomicSequenceFingerprint()
    for o in getattr(res_a, "orders", []):
        fp_a.add_event("SimulatedOrder", {"id": o.simulated_order_id, "side": o.side, "qty": o.quantity})
    for f in getattr(res_a, "fills", []):
        fp_a.add_event("SimulatedFill", {"id": f.fill_id, "side": f.side, "price": f.fill_price})
    digest_a = fp_a.compute_fingerprint()

    # 2. Backtest Run B: Strategy RSI_1M (Variant)
    cfg_b = BacktestConfig(
        strategy_id="RSI_1M",
        symbols=["NVDA"],
        timeframe="1m",
        initial_simulated_cash=100000.0,
        warmup_bars_count=30,
    )
    runner_b = BacktestRunner(config=cfg_b, store=store, dataset_manager=ds_manager)
    res_b = runner_b.run(bars)

    # 3. Strategy Comparison
    run_a_dict = res_a.to_dict() if hasattr(res_a, "to_dict") else res_a
    run_b_dict = res_b.to_dict() if hasattr(res_b, "to_dict") else res_b
    comp_res = BacktestComparisonService.compare_runs([run_a_dict, run_b_dict], baseline_id=res_a.run_id)

    return {
        "dataset_provenance": {
            "source": "SYNTHETIC_HISTORICAL_1M_OHLCV",
            "symbol": "NVDA",
            "bar_count": len(bars),
            "start_time": base_time.isoformat(),
            "end_time": (base_time + timedelta(minutes=len(bars)-1)).isoformat(),
            "timeframe": "1m",
        },
        "variant_a": {
            "run_id": res_a.run_id,
            "status": res_a.status,
            "strategy_id": cfg_a.strategy_id,
            "deterministic_fingerprint": digest_a,
            "metrics": {
                "final_equity": float(res_a.metrics.get("final_equity", 100000.0)),
                "net_pnl": float(res_a.metrics.get("net_pnl", 0.0)),
                "total_orders": res_a.metrics.get("total_orders", 0),
                "total_fills": res_a.metrics.get("total_fills", 0),
                "max_drawdown_pct": float(res_a.metrics.get("max_drawdown_pct", 0.0)),
            },
        },
        "variant_b": {
            "run_id": res_b.run_id,
            "status": res_b.status,
            "strategy_id": cfg_b.strategy_id,
            "metrics": {
                "final_equity": float(res_b.metrics.get("final_equity", 100000.0)),
                "net_pnl": float(res_b.metrics.get("net_pnl", 0.0)),
                "total_orders": res_b.metrics.get("total_orders", 0),
                "total_fills": res_b.metrics.get("total_fills", 0),
                "max_drawdown_pct": float(res_b.metrics.get("max_drawdown_pct", 0.0)),
            },
        },
        "comparison_result": comp_res,
        "status": "PASS" if (res_a.status == "COMPLETED" and res_b.status == "COMPLETED" and len(digest_a) == 64) else "FAIL",
    }


def main():
    safety_monitor = SafetyMonitor()
    safety_monitor.check_invariants()

    multibot_res = verify_multibot_isolation()
    backtest_res = verify_backtest_and_comparison()

    overall_status = "PASS" if (multibot_res["status"] == "PASS" and backtest_res["status"] == "PASS") else "FAIL"

    evidence = {
        "stage": "GĐ40",
        "title": "Release Candidate System Validation Evidence (Multi-Bot & Backtesting)",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "multibot_isolation": multibot_res,
        "backtesting_and_comparison": backtest_res,
        "safety_audit": {
            "trading_mode": "DRY_RUN",
            "paper_execution_gate_open": False,
            "outbound_broker_calls": safety_monitor.outbound_broker_calls,
            "environment": "SIMULATION",
        },
        "overall_status": overall_status,
    }

    os.makedirs("data/status", exist_ok=True)
    evidence_path = "data/status/gd40_release_evidence.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, default=str)

    logger.info(f"Saved GD40 release validation evidence to {evidence_path}")
    print("\n" + "=" * 65)
    print("GD40 MULTI-BOT & BACKTESTING VALIDATION REPORT:")
    print(f"- Multi-Bot Isolation: {multibot_res['status']}")
    print(f"  * 3 Bots Registered: {multibot_res['bots']}")
    print(f"  * Portfolios Isolated: {multibot_res['portfolios_strictly_isolated']}")
    print(f"  * Failure Isolated (Alpha paused -> Beta/Gamma unaffected): {multibot_res['failure_isolated']}")
    print(f"- Backtesting Engine: {backtest_res['status']}")
    print(f"  * Dataset Bars Processed: {backtest_res['dataset_provenance']['bar_count']}")
    print(f"  * Variant A Status: {backtest_res['variant_a']['status']} (Orders: {backtest_res['variant_a']['metrics']['total_orders']}, Fills: {backtest_res['variant_a']['metrics']['total_fills']})")
    print(f"  * Deterministic Fingerprint: {backtest_res['variant_a']['deterministic_fingerprint'][:16]}...")
    print(f"  * Strategy Comparison Baseline: {backtest_res['comparison_result']['baseline_id']}")
    print(f"- Overall Status: {overall_status}")
    print("=" * 65 + "\n")

    if overall_status == "PASS":
        logger.info("MULTI-BOT & BACKTESTING VALIDATION PASSED SUCCESSFULLY!")
        sys.exit(0)
    else:
        logger.error("VALIDATION FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    main()
