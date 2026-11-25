"""
scripts/verify_gd39_deterministic_e2e.py — Standalone Deterministic E2E Trading Verification (GĐ39)
Executes a transparent synthetic 1m fixture scenario producing an actual BUY trade:
Final 1m bars -> MA Bullish Crossover -> SignalDecision ACCEPTED -> SimulationOrderIntent ->
SimulatedOrder (WORKING) -> Next-bar SimulatedFill with fees & slippage -> Portfolio Position & Cash -> Reconciliation BALANCED.
Saves evidence to data/status/gd39_e2e_evidence.json.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from libs.bot.multibot.supervisor import MultiBotSupervisor
from libs.bot.multibot.registry import BotDefinition
from libs.bot.reliability.scenarios import ReliabilityScenarios
from libs.bot.reliability.safety_monitor import SafetyMonitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("e2e-trade-verification")

def main():
    logger.info("Executing Deterministic E2E Trading Pipeline Verification...")

    # Safety checks
    safety_monitor = SafetyMonitor()
    safety_monitor.check_invariants()

    temp_dir = tempfile.mkdtemp()
    supervisor = MultiBotSupervisor(base_dir=temp_dir)
    bot_id = "bot_deterministic_e2e"

    bot_def = BotDefinition(
        bot_id=bot_id,
        strategy_id="MA_CROSS_1M",
        symbols=["NVDA"],
        initial_simulated_cash=100000.0,
    )
    supervisor.registry.register_bot(bot_def)
    supervisor.start_bot(bot_id)

    res = ReliabilityScenarios.run_deterministic_e2e_trading_scenario(
        supervisor=supervisor,
        bot_id=bot_id,
        symbol="NVDA",
        initial_cash=100000.0,
    )

    supervisor.stop_bot(bot_id)

    # Attach metadata
    res["verified_at"] = datetime.now(timezone.utc).isoformat()
    res["trading_mode"] = "DRY_RUN"
    res["paper_execution_gate_open"] = False
    res["outbound_broker_calls"] = safety_monitor.outbound_broker_calls
    res["environment"] = "SIMULATION"

    os.makedirs("data/status", exist_ok=True)
    evidence_path = "data/status/gd39_e2e_evidence.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, default=str)

    logger.info(f"Saved E2E trade evidence to {evidence_path}")
    print("\n" + "=" * 60)
    print("DETERMINISTIC E2E TRADING VERIFICATION REPORT:")
    print(f"- Scenario: {res['scenario']}")
    print(f"- Fixture: {res['fixture_type']}")
    print(f"- Bars Processed: {res['bars_processed']}")
    print(f"- Orders Created: {res['orders_count']}")
    print(f"- Fills Created: {res['fills_count']}")
    for f in res["fills"]:
        print(f"  * Fill: id={f['fill_id']}, qty={f['qty']}, price={f['price']}, fee={f['fee']}, slippage={f['slippage']}, side={f['side']}")
    print(f"- Cash Before: {res['portfolio_before']['cash']} -> Cash After: {res['portfolio_after']['cash']}")
    print(f"- Positions: {res['portfolio_after']['positions']}")
    print(f"- Fees Charged: {res['portfolio_after']['total_fees']}")
    print(f"- Next-Bar Execution Verified: {res['next_bar_execution_verified']}")
    print(f"- Reconciliation Status: {'BALANCED' if res['reconciliation']['is_balanced'] else 'DISCREPANCY'}")
    print(f"- Final Status: {res['status']}")
    print("=" * 60 + "\n")

    if res["status"] == "PASS":
        logger.info("DETERMINISTIC E2E TRADING VERIFIED SUCCESSFULLY!")
        sys.exit(0)
    else:
        logger.error("DETERMINISTIC E2E TRADING FAILED!")
        sys.exit(1)

if __name__ == "__main__":
    main()
