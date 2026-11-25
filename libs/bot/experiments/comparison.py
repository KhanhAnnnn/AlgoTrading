"""
libs/bot/experiments/comparison.py — Multi-Run Comparison & Research Metrics (GĐ38)
Computes comparative KPI tables, metric deltas relative to baseline, and aligns curves
with zero-denominator safeguards.
"""

from typing import Dict, List, Any, Optional
import math
import logging

from libs.bot.experiments.comparability import ComparabilityEngine, ComparabilityResult

logger = logging.getLogger("backtest-comparison")


class BacktestComparisonService:
    """
    Generates unified performance tables, relative delta calculations,
    and comparative curve overlays for backtest runs and experiment variants.
    """

    @staticmethod
    def _safe_float(val: Any, default: float = 0.0) -> float:
        if val is None:
            return default
        try:
            f = float(val)
            return 0.0 if math.isnan(f) or math.isinf(f) else f
        except (ValueError, TypeError):
            return default

    @classmethod
    def compare_runs(
        cls,
        runs: List[Dict[str, Any]],
        baseline_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compares multiple backtest runs or experiment variants.
        If baseline_id is not specified, the first run in the list is treated as the baseline.
        """
        if not runs:
            return {"runs_count": 0, "comparison_table": [], "comparability": "NO_RUNS"}

        # Find baseline
        baseline = None
        if baseline_id:
            for r in runs:
                if r.get("variant_id") == baseline_id or r.get("run_id") == baseline_id:
                    baseline = r
                    break
        if not baseline:
            baseline = runs[0]

        base_metrics = baseline.get("metrics") or baseline.get("result_summary") or {}
        base_sharpe = cls._safe_float(base_metrics.get("sharpe_ratio"))
        base_return = cls._safe_float(base_metrics.get("total_return_pct") or base_metrics.get("total_return"))
        base_drawdown = cls._safe_float(base_metrics.get("max_drawdown_pct") or base_metrics.get("max_drawdown"))
        base_win_rate = cls._safe_float(base_metrics.get("win_rate_pct") or base_metrics.get("win_rate"))
        base_profit_factor = cls._safe_float(base_metrics.get("profit_factor"))

        comparison_table: List[Dict[str, Any]] = []
        comparability_results: Dict[str, Any] = {}

        for r in runs:
            r_id = r.get("variant_id") or r.get("run_id") or "unknown"
            metrics = r.get("metrics") or r.get("result_summary") or {}

            sharpe = cls._safe_float(metrics.get("sharpe_ratio"))
            ret = cls._safe_float(metrics.get("total_return_pct") or metrics.get("total_return"))
            mdd = cls._safe_float(metrics.get("max_drawdown_pct") or metrics.get("max_drawdown"))
            sortino = cls._safe_float(metrics.get("sortino_ratio"))
            win_rate = cls._safe_float(metrics.get("win_rate_pct") or metrics.get("win_rate"))
            trades = int(cls._safe_float(metrics.get("total_trades")))
            pf = cls._safe_float(metrics.get("profit_factor"))
            calmar = cls._safe_float(metrics.get("calmar_ratio"))

            # Calculate deltas relative to baseline
            delta_sharpe = round(sharpe - base_sharpe, 4)
            delta_return = round(ret - base_return, 4)
            delta_mdd = round(mdd - base_drawdown, 4)
            delta_win_rate = round(win_rate - base_win_rate, 4)
            delta_pf = round(pf - base_profit_factor, 4)

            # Evaluate comparability against baseline
            comp_eval = ComparabilityEngine.evaluate(baseline, r)
            comparability_results[r_id] = {
                "is_comparable": comp_eval.is_comparable,
                "status": comp_eval.status,
                "reason_codes": comp_eval.reason_codes,
            }

            row = {
                "run_id": r_id,
                "name": r.get("variant_name") or r.get("name") or r_id,
                "preset_id": r.get("preset_id", ""),
                "strategy_id": r.get("strategy_id", ""),
                "is_baseline": (r_id == (baseline.get("variant_id") or baseline.get("run_id"))),
                "is_comparable": comp_eval.is_comparable,
                "comparability_status": comp_eval.status,
                "comparability_reasons": comp_eval.reason_codes,
                # Absolute metrics
                "total_return_pct": ret,
                "sharpe_ratio": sharpe,
                "sortino_ratio": sortino,
                "max_drawdown_pct": mdd,
                "win_rate_pct": win_rate,
                "total_trades": trades,
                "profit_factor": pf,
                "calmar_ratio": calmar,
                # Relative deltas
                "delta_sharpe": delta_sharpe,
                "delta_return_pct": delta_return,
                "delta_max_drawdown_pct": delta_mdd,
                "delta_win_rate_pct": delta_win_rate,
                "delta_profit_factor": delta_pf,
            }
            comparison_table.append(row)

        return {
            "baseline_id": baseline.get("variant_id") or baseline.get("run_id"),
            "runs_count": len(runs),
            "comparison_table": comparison_table,
            "comparability_summary": comparability_results,
        }

    @classmethod
    def align_equity_curves(cls, runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extracts and aligns equity curves across runs for graphical overlay.
        Normalizes initial equity to 1.0 or 100,000 for relative comparison.
        """
        series: Dict[str, List[Dict[str, Any]]] = {}
        for r in runs:
            r_id = r.get("variant_id") or r.get("run_id") or "unknown"
            curve = r.get("equity_curve") or []
            normalized = []
            init_val = None
            for pt in curve:
                val = cls._safe_float(pt.get("equity") or pt.get("portfolio_value"))
                if init_val is None and val > 0:
                    init_val = val
                norm_equity = (val / init_val * 100.0) if init_val and init_val > 0 else 100.0
                normalized.append({
                    "timestamp": pt.get("timestamp") or pt.get("time"),
                    "equity": val,
                    "normalized_equity": round(norm_equity, 4),
                })
            series[r_id] = normalized
        return {"curves": series}
