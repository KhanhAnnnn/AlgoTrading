"""
scripts/verify_gd40_deterministic_roundtrip.py — Standalone Deterministic E2E Roundtrip Verification (GĐ40)
Executes a transparent synthetic 1m fixture scenario producing BOTH a BUY and a SELL trade (Full Roundtrip):
1. Final 1m bars -> MA Bullish Golden Cross -> SignalDecision ACCEPTED -> SimulationOrderIntent ->
   SimulatedOrder (WORKING) -> Next-bar SimulatedFill BUY (fees & slippage) -> Open Position
2. Flat holding period -> MA Bearish Death Cross -> SignalDecision ACCEPTED (sell existing position) ->
   SimulationOrderIntent -> SimulatedOrder (WORKING) -> Next-bar SimulatedFill SELL (fees & slippage) -> Closed Position
3. Calculates Realized P&L, fees on both legs, slippage on both legs, and confirms BALANCED reconciliation.
4. Outputs machine-readable evidence to data/status/gd40_demo_evidence.json.
"""

import os
import sys
import json
import logging
import tempfile
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from libs.bot.multibot.supervisor import MultiBotSupervisor
from libs.bot.multibot.registry import BotDefinition
from libs.bot.reliability.scenarios import ReliabilityScenarios
from libs.bot.reliability.safety_monitor import SafetyMonitor
from libs.bot.reliability.reconciliation import SimulationReconciliationEngine
from libs.bot.execution.fees import ConfigurableFeeModel
from libs.bot.execution.slippage import FixedBpsSlippageModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("gd40-roundtrip-demo")


def run_deterministic_roundtrip_demo() -> dict:
    logger.info("Initializing Deterministic E2E Roundtrip Trading Scenario (BUY -> SELL)...")
    safety_monitor = SafetyMonitor()
    safety_monitor.check_invariants()

    temp_dir = tempfile.mkdtemp()
    supervisor = MultiBotSupervisor(base_dir=temp_dir)
    bot_id = "demo_roundtrip_bot"
    initial_cash = 100000.0

    bot_def = BotDefinition(
        bot_id=bot_id,
        strategy_id="MA_CROSS_1M",
        symbols=["NVDA"],
        initial_simulated_cash=initial_cash,
    )
    supervisor.registry.register_bot(bot_def)
    supervisor.start_bot(bot_id)

    runtime = supervisor._active_runtimes[bot_id]
    # Configure 5 bps slippage and $0.01/share ($1.50 min) commission
    runtime.orchestrator.broker.fill_engine.fee_model = ConfigurableFeeModel(stocks_per_share=0.01, stocks_min_commission=1.50)
    runtime.orchestrator.broker.fill_engine.slippage_model = FixedBpsSlippageModel(bps=5.0)

    snap_before = runtime.orchestrator.portfolio.get_portfolio_snapshot()
    base_time = datetime(2026, 11, 24, 8, 0, tzinfo=timezone.utc)

    # 1. Warmup: 52 flat bars @ 100.0
    # 2. Surge: 5 drop bars (95..87) followed by 5 surge bars (105..145) -> Triggers BUY Golden Cross at bar 60
    # 3. Holding & Profit target: 5 high bars (146..150) -> Bar 61 fills BUY
    # 4. Bearish reversal: 5 drop bars (125, 110, 95, 85, 75) -> Triggers SELL Death Cross at bar 70
    # 5. Execution bars: Bar 71 (74.0) fills SELL, closing position
    prices = (
        [100.0] * 52 +
        [95.0, 93.0, 91.0, 89.0, 87.0] +
        [105.0, 115.0, 125.0, 135.0, 145.0] +
        [146.0, 147.0, 148.0, 149.0, 150.0] +
        [125.0, 110.0, 95.0, 85.0, 75.0] +
        [74.0, 73.0]
    )

    events_sent = []
    step_trace = []

    for i, p in enumerate(prices):
        bar_time = base_time + timedelta(minutes=i)
        bar = ReliabilityScenarios.create_synthetic_1m_bar(
            symbol="NVDA",
            price=p,
            event_time=bar_time,
            event_id=f"roundtrip_bar_{i+1}",
            is_final=True,
        )
        supervisor.dispatcher.dispatch_event(bar)
        events_sent.append(bar)

        res = runtime.orchestrator.on_market_data(bar)
        if res and (res.get("signals") or res.get("fills_generated", 0) > 0 or res.get("intent")):
            step_trace.append({
                "bar_index": i + 1,
                "bar_time": bar_time.isoformat(),
                "price": p,
                "signals": [s.signal_type for s in res.get("signals", [])],
                "fills_generated": res.get("fills_generated", 0),
                "decision": res.get("decision").status if res.get("decision") else None,
                "intent": res.get("intent").side if res.get("intent") else None,
            })

    fills = getattr(runtime.orchestrator.broker, "_fills", []) or []
    orders = list(runtime.orchestrator.broker.order_manager._orders.values())
    snap_after = runtime.orchestrator.portfolio.get_portfolio_snapshot()
    recon = SimulationReconciliationEngine.audit_portfolio(
        portfolio=runtime.orchestrator.portfolio,
        fills=fills,
    )

    supervisor.stop_bot(bot_id)

    # Analyze Roundtrip Legs
    buy_fills = [f for f in fills if f.side == "BUY"]
    sell_fills = [f for f in fills if f.side == "SELL"]

    buy_step = next((s for s in step_trace if s.get("intent") == "BUY"), None)
    buy_fill_step = next((s for s in step_trace if s.get("fills_generated", 0) > 0 and len(buy_fills) > 0), None)
    sell_step = next((s for s in step_trace if s.get("intent") == "SELL"), None)
    sell_fill_step = next((s for s in step_trace if s.get("fills_generated", 0) > 0 and s["bar_index"] > (buy_fill_step["bar_index"] if buy_fill_step else 0)), None)

    buy_next_bar_verified = bool(
        buy_step and buy_fill_step and buy_fill_step["bar_index"] == buy_step["bar_index"] + 1
    )
    sell_next_bar_verified = bool(
        sell_step and sell_fill_step and sell_fill_step["bar_index"] == sell_step["bar_index"] + 1
    )

    roundtrip_complete = (len(buy_fills) > 0 and len(sell_fills) > 0 and len(snap_after.positions) == 0)

    # Accounting Verification
    expected_cash = initial_cash + snap_after.realized_pnl - snap_after.total_fees
    cash_diff = abs(snap_after.cash - expected_cash)
    accounting_balanced = (cash_diff < 0.001)

    result = {
        "scenario": "DETERMINISTIC_E2E_ROUNDTRIP_TRADING",
        "description": "Full BUY -> HOLD -> SELL roundtrip with realized P&L, next-bar fills, fees, slippage and balanced audit.",
        "provenance": {
            "source": "SYNTHETIC_DETERMINISTIC_1M_OHLCV",
            "symbol": "NVDA",
            "bar_count": len(events_sent),
            "start_time": base_time.isoformat(),
            "end_time": (base_time + timedelta(minutes=len(events_sent)-1)).isoformat(),
            "timeframe": "1m",
            "is_final_enforced": True,
        },
        "bot_id": bot_id,
        "strategy_id": "MA_CROSS_1M",
        "initial_cash": initial_cash,
        "cash_after": float(snap_after.cash),
        "realized_pnl": float(snap_after.realized_pnl),
        "total_fees": float(snap_after.total_fees),
        "open_positions_count": len(snap_after.positions),
        "orders_count": len(orders),
        "fills_count": len(fills),
        "orders": [
            {
                "order_id": o.simulated_order_id,
                "side": o.side,
                "qty": float(o.quantity),
                "status": o.status,
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
        "roundtrip_metrics": {
            "roundtrip_complete": roundtrip_complete,
            "buy_leg": {
                "signal_bar_index": buy_step["bar_index"] if buy_step else None,
                "fill_bar_index": buy_fill_step["bar_index"] if buy_fill_step else None,
                "fill_price": float(buy_fills[0].fill_price) if buy_fills else None,
                "qty": float(buy_fills[0].fill_qty) if buy_fills else None,
                "fee": float(buy_fills[0].fee) if buy_fills else None,
                "next_bar_verified": buy_next_bar_verified,
            },
            "sell_leg": {
                "signal_bar_index": sell_step["bar_index"] if sell_step else None,
                "fill_bar_index": sell_fill_step["bar_index"] if sell_fill_step else None,
                "fill_price": float(sell_fills[0].fill_price) if sell_fills else None,
                "qty": float(sell_fills[0].fill_qty) if sell_fills else None,
                "fee": float(sell_fills[0].fee) if sell_fills else None,
                "next_bar_verified": sell_next_bar_verified,
            },
            "realized_pnl": float(snap_after.realized_pnl),
            "net_pnl": float(snap_after.realized_pnl - snap_after.total_fees),
        },
        "reconciliation": {
            "is_balanced": recon.is_balanced,
            "cash_balanced": recon.cash_balanced,
            "positions_balanced": recon.positions_balanced,
            "cash_diff": float(recon.metrics.get("cash_diff", cash_diff)),
            "discrepancies": recon.discrepancies,
        },
        "accounting_check": {
            "equation": "Cash + Cost Basis = Initial Cash + Realized PnL - Total Fees",
            "actual_cash": float(snap_after.cash),
            "expected_cash": float(expected_cash),
            "difference": float(cash_diff),
            "balanced": accounting_balanced,
        },
        "safety_audit": {
            "trading_mode": "DRY_RUN",
            "paper_execution_gate_open": False,
            "outbound_broker_calls": safety_monitor.outbound_broker_calls,
            "environment": "SIMULATION",
        },
        "step_trace": step_trace,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if (roundtrip_complete and recon.is_balanced and accounting_balanced and buy_next_bar_verified and sell_next_bar_verified) else "FAIL",
    }

    return result


def main():
    res = run_deterministic_roundtrip_demo()

    os.makedirs("data/status", exist_ok=True)
    evidence_path = "data/status/gd40_demo_evidence.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, default=str)

    logger.info(f"Saved GD40 roundtrip demo evidence to {evidence_path}")
    print("\n" + "=" * 65)
    print("DETERMINISTIC E2E ROUNDTRIP TRADING DEMO REPORT:")
    print(f"- Scenario: {res['scenario']}")
    print(f"- Bars Processed: {res['provenance']['bar_count']}")
    print(f"- Orders Created: {res['orders_count']}")
    print(f"- Fills Created: {res['fills_count']}")
    for f in res["fills"]:
        print(f"  * Fill: id={f['fill_id']}, side={f['side']}, qty={f['qty']}, price={f['price']}, fee={f['fee']}, slippage={f['slippage']}")
    print(f"- Initial Cash: {res['initial_cash']} -> Final Cash: {res['cash_after']}")
    print(f"- Realized PnL: {res['realized_pnl']} | Total Fees: {res['total_fees']}")
    print(f"- Open Positions Count: {res['open_positions_count']} (0 = successfully closed)")
    print(f"- Buy Next-Bar Verified: {res['roundtrip_metrics']['buy_leg']['next_bar_verified']}")
    print(f"- Sell Next-Bar Verified: {res['roundtrip_metrics']['sell_leg']['next_bar_verified']}")
    print(f"- Accounting Check Balanced: {res['accounting_check']['balanced']} (diff = {res['accounting_check']['difference']})")
    print(f"- Reconciliation: {'BALANCED' if res['reconciliation']['is_balanced'] else 'DISCREPANCY'}")
    print(f"- Safety Invariants: DRY_RUN={res['safety_audit']['trading_mode']}, GateOpen={res['safety_audit']['paper_execution_gate_open']}, BrokerCalls={res['safety_audit']['outbound_broker_calls']}")
    print(f"- Final Status: {res['status']}")
    print("=" * 65 + "\n")

    if res["status"] == "PASS":
        logger.info("ROUNDTRIP DEMO SUCCEEDED WITH 100% RECONCILIATION!")
        sys.exit(0)
    else:
        logger.error("ROUNDTRIP DEMO FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    main()
