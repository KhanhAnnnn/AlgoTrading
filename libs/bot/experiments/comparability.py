"""
libs/bot/experiments/comparability.py — Fair Comparison Rules & Comparability Engine (GĐ38)
Evaluates whether backtest runs or experiment variants share identical benchmark conditions:
dataset version/hash, date range, asset universe, timeframe, fee/slippage models.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger("backtest-comparability")


@dataclass
class ComparabilityResult:
    """Outcome of fair comparison evaluation between two backtest configurations or runs."""
    is_comparable: bool
    status: str  # "DIRECTLY_COMPARABLE" or "NOT_DIRECTLY_COMPARABLE"
    reason_codes: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class ComparabilityEngine:
    """
    Enforces scientific validity and fair comparison rules across backtesting runs.
    Disallows direct ranking or overlay if underlying market conditions or execution assumptions differ.
    """

    @staticmethod
    def evaluate(
        config_a: Dict[str, Any],
        config_b: Dict[str, Any],
    ) -> ComparabilityResult:
        reasons: List[str] = []
        details: Dict[str, Any] = {}

        # 1. Dataset version or hash
        data_a = config_a.get("dataset_hash") or config_a.get("dataset_version") or config_a.get("dataset_reference")
        data_b = config_b.get("dataset_hash") or config_b.get("dataset_version") or config_b.get("dataset_reference")
        if data_a and data_b and data_a != data_b:
            reasons.append("DATASET_MISMATCH")
            details["dataset"] = {"config_a": data_a, "config_b": data_b}

        # 2. Date range (start_time, end_time)
        start_a = str(config_a.get("start_time") or (config_a.get("date_range", {}) or {}).get("start_time"))
        start_b = str(config_b.get("start_time") or (config_b.get("date_range", {}) or {}).get("start_time"))
        end_a = str(config_a.get("end_time") or (config_a.get("date_range", {}) or {}).get("end_time"))
        end_b = str(config_b.get("end_time") or (config_b.get("date_range", {}) or {}).get("end_time"))

        if start_a != start_b or end_a != end_b:
            reasons.append("DATE_RANGE_MISMATCH")
            details["date_range"] = {
                "config_a": {"start": start_a, "end": end_a},
                "config_b": {"start": start_b, "end": end_b},
            }

        # 3. Asset universe / symbols
        syms_a = sorted(config_a.get("symbols") or [])
        syms_b = sorted(config_b.get("symbols") or [])
        if syms_a != syms_b:
            reasons.append("UNIVERSE_MISMATCH")
            details["symbols"] = {"config_a": syms_a, "config_b": syms_b}

        # 4. Timeframe (1m invariant)
        tf_a = config_a.get("timeframe", "1m")
        tf_b = config_b.get("timeframe", "1m")
        if tf_a != tf_b:
            reasons.append("TIMEFRAME_MISMATCH")
            details["timeframe"] = {"config_a": tf_a, "config_b": tf_b}

        # 5. Fee model
        fee_a = config_a.get("fee_model", "DEFAULT")
        fee_b = config_b.get("fee_model", "DEFAULT")
        if fee_a != fee_b:
            reasons.append("FEE_MODEL_MISMATCH")
            details["fee_model"] = {"config_a": fee_a, "config_b": fee_b}

        # 6. Slippage model
        slip_a = config_a.get("slippage_model", "DEFAULT")
        slip_b = config_b.get("slippage_model", "DEFAULT")
        if slip_a != slip_b:
            reasons.append("SLIPPAGE_MODEL_MISMATCH")
            details["slippage_model"] = {"config_a": slip_a, "config_b": slip_b}

        # 7. Initial simulated capital
        cap_a = float(config_a.get("initial_simulated_cash") or config_a.get("initial_capital", 100000.0))
        cap_b = float(config_b.get("initial_simulated_cash") or config_b.get("initial_capital", 100000.0))
        if abs(cap_a - cap_b) > 0.01:
            reasons.append("CAPITAL_MISMATCH")
            details["initial_capital"] = {"config_a": cap_a, "config_b": cap_b}

        is_comparable = len(reasons) == 0
        return ComparabilityResult(
            is_comparable=is_comparable,
            status="DIRECTLY_COMPARABLE" if is_comparable else "NOT_DIRECTLY_COMPARABLE",
            reason_codes=reasons,
            details=details,
        )
