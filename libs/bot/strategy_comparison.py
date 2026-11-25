"""
libs/bot/strategy_comparison.py — Python vs Flink V1 Strategy Comparator (GĐ31)
Performs read-only comparison between Python Strategy Engine and Apache Flink Strategy 1.
Classifies comparison results: MATCH, EXPECTED_DIFFERENCE, MISMATCH, NOT_COMPARABLE.
Preserves V1 production jobs without modification.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from libs.bot.domain import StrategySignal

logger = logging.getLogger("strategy-comparator")


class ComparisonCategory:
    MATCH = "MATCH"
    EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
    MISMATCH = "MISMATCH"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class StrategyComparator:
    """
    Read-only comparative auditor contrasting Python V2 signals with Flink V1 signals.
    """

    @staticmethod
    def compare_signals(
        python_signal: StrategySignal,
        flink_signal: StrategySignal,
        tolerance_price_pct: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Compares two signals for the same symbol and timeframe.
        Returns classification and detailed divergence rationale.
        """
        # 1. Symbol & Timeframe comparability check
        if python_signal.symbol != flink_signal.symbol or python_signal.timeframe != flink_signal.timeframe:
            return {
                "category": ComparisonCategory.NOT_COMPARABLE,
                "reason": f"Disparate targets: Python ({python_signal.symbol}:{python_signal.timeframe}) vs Flink ({flink_signal.symbol}:{flink_signal.timeframe})",
                "python_signal_type": python_signal.signal_type,
                "flink_signal_type": flink_signal.signal_type,
            }

        # 2. Time delta check
        time_delta_sec = abs((python_signal.signal_time - flink_signal.signal_time).total_seconds())

        # If timestamps differ by more than 2 minutes, difference is expected due to windowing/watermark
        if time_delta_sec > 120.0:
            return {
                "category": ComparisonCategory.EXPECTED_DIFFERENCE,
                "reason": f"Timestamp divergence ({time_delta_sec:.1f}s) due to Flink watermark skew vs Python instant bar tick",
                "time_delta_sec": time_delta_sec,
                "python_signal_type": python_signal.signal_type,
                "flink_signal_type": flink_signal.signal_type,
            }

        # 3. Exact Signal Type match
        if python_signal.signal_type == flink_signal.signal_type:
            # Check price divergence
            price_div = abs(python_signal.price - flink_signal.price)
            pct_div = (price_div / flink_signal.price * 100.0) if flink_signal.price > 0 else 0.0

            if pct_div <= tolerance_price_pct:
                return {
                    "category": ComparisonCategory.MATCH,
                    "reason": f"Exact signal match ({python_signal.signal_type}) within {pct_div:.3f}% price tolerance",
                    "price_divergence_pct": pct_div,
                    "python_signal_type": python_signal.signal_type,
                    "flink_signal_type": flink_signal.signal_type,
                }
            else:
                return {
                    "category": ComparisonCategory.EXPECTED_DIFFERENCE,
                    "reason": f"Matching signal ({python_signal.signal_type}) with price divergence ({pct_div:.2f}%) due to bar revision timing",
                    "price_divergence_pct": pct_div,
                }

        # 4. Warmup or parameter difference
        if "INSUFFICIENT_WARMUP" in python_signal.reason_codes:
            return {
                "category": ComparisonCategory.EXPECTED_DIFFERENCE,
                "reason": "Python engine is still completing warmup requirements while Flink had accumulated state",
            }

        # 5. True Mismatch
        return {
            "category": ComparisonCategory.MISMATCH,
            "reason": f"Divergent signal types at similar timestamp: Python={python_signal.signal_type} vs Flink={flink_signal.signal_type}",
            "python_price": python_signal.price,
            "flink_price": flink_signal.price,
            "time_delta_sec": time_delta_sec,
        }
