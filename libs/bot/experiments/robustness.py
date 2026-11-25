"""
libs/bot/experiments/robustness.py — Strategy Robustness & Temporal Split Analyzer (GĐ38)
Evaluates parameter sensitivity grids and in-sample vs out-of-sample temporal splits.
Strictly guarantees no data leakage and strictly disallows automated live deployment.
"""

from typing import Dict, List, Any, Optional, Tuple, Callable
import math
import statistics
import logging

logger = logging.getLogger("strategy-robustness")


class StrategyRobustnessAnalyzer:
    """
    Assesses quantitative strategy robustness against overfitting and parameter brittleness.
    """

    @staticmethod
    def analyze_parameter_sensitivity(
        base_parameters: Dict[str, Any],
        parameter_results: List[Dict[str, Any]],
        metric_key: str = "sharpe_ratio",
    ) -> Dict[str, Any]:
        """
        Analyzes the distribution of performance across a parameter neighborhood.
        Calculates mean, standard deviation, min, max, and coefficient of variation.
        """
        if not parameter_results:
            return {"status": "NO_DATA", "robustness_score": 0.0}

        values: List[float] = []
        for res in parameter_results:
            m = res.get("metrics") or res.get("result_summary") or {}
            val = m.get(metric_key)
            if val is not None:
                try:
                    f = float(val)
                    if not (math.isnan(f) or math.isinf(f)):
                        values.append(f)
                except Exception:
                    pass

        if not values:
            return {"status": "NO_VALID_METRICS", "robustness_score": 0.0}

        mean_val = statistics.mean(values)
        stdev_val = statistics.stdev(values) if len(values) > 1 else 0.0
        cv = (stdev_val / abs(mean_val)) if abs(mean_val) > 1e-6 else 0.0

        # High variance in metric across adjacent parameters indicates parameter brittleness / overfitting
        is_robust = cv < 0.35 and min(values) > 0.0

        return {
            "metric_evaluated": metric_key,
            "sample_count": len(values),
            "mean": round(mean_val, 4),
            "stdev": round(stdev_val, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "coefficient_of_variation": round(cv, 4),
            "is_robust": is_robust,
            "robustness_score": round(max(0.0, 1.0 - cv), 4),
            "brittleness_warning": not is_robust,
        }

    @staticmethod
    def split_dataset_temporal(
        bars: List[Any],
        train_ratio: float = 0.60,
        val_ratio: float = 0.20,
        test_ratio: float = 0.20,
    ) -> Tuple[List[Any], List[Any], List[Any]]:
        """
        Partitions historical bars sequentially into Train (In-Sample), Validation, and Test (Out-of-Sample).
        Strict chronological ordering prevents lookahead bias and data leakage.
        """
        total = len(bars)
        if total == 0:
            return [], [], []

        n_train = int(total * train_ratio)
        n_val = int(total * val_ratio)

        train_bars = bars[:n_train]
        val_bars = bars[n_train : n_train + n_val]
        test_bars = bars[n_train + n_val :]

        logger.info(
            f"Temporal Split: total={total}, train={len(train_bars)}, val={len(val_bars)}, test={len(test_bars)}"
        )
        return train_bars, val_bars, test_bars

    @staticmethod
    def evaluate_temporal_performance(
        in_sample_metrics: Dict[str, Any],
        out_of_sample_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluates performance degradation from In-Sample (IS) to Out-of-Sample (OOS).
        """
        is_sharpe = float(in_sample_metrics.get("sharpe_ratio", 0.0) or 0.0)
        oos_sharpe = float(out_of_sample_metrics.get("sharpe_ratio", 0.0) or 0.0)

        is_return = float(in_sample_metrics.get("total_return_pct", 0.0) or 0.0)
        oos_return = float(out_of_sample_metrics.get("total_return_pct", 0.0) or 0.0)

        # Degradation ratio: OOS / IS
        degradation_ratio = (oos_sharpe / is_sharpe) if is_sharpe > 0 else 0.0

        # Assess overfitting risk
        if is_sharpe > 1.5 and oos_sharpe < 0.2:
            overfitting_risk = "HIGH"
            recommendation = "REJECT_OVERFIT: Severe degradation between in-sample and out-of-sample."
        elif degradation_ratio < 0.40:
            overfitting_risk = "MODERATE"
            recommendation = "NEEDS_TUNING: Notable performance decay out-of-sample."
        else:
            overfitting_risk = "LOW"
            recommendation = "ACCEPTABLE: Generalizes acceptably to out-of-sample data."

        return {
            "in_sample": {
                "sharpe_ratio": round(is_sharpe, 4),
                "total_return_pct": round(is_return, 4),
            },
            "out_of_sample": {
                "sharpe_ratio": round(oos_sharpe, 4),
                "total_return_pct": round(oos_return, 4),
            },
            "sharpe_degradation_ratio": round(degradation_ratio, 4),
            "overfitting_risk": overfitting_risk,
            "recommendation": recommendation,
            "auto_deploy_allowed": False,  # Strict invariant: Never auto-deploy
        }
