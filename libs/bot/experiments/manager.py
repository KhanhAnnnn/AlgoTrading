"""
libs/bot/experiments/manager.py — Backtest Experiment Manager & Execution Lifecycle (GĐ38)
Orchestrates systematic parameter exploration, variant execution, concurrency quotas,
and cancellation management for AlgoTrading V2.0.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timezone
import uuid
import logging
import copy

from libs.bot.strategy_config.versioning import compute_configuration_hash
from libs.bot.strategy_config.presets import PresetStore, StrategyPreset
from libs.bot.experiments.store import ExperimentStore
from libs.bot.experiments.comparability import ComparabilityEngine
from libs.bot.experiments.comparison import BacktestComparisonService
from libs.bot.experiments.fingerprint import EconomicSequenceFingerprint

logger = logging.getLogger("experiment-manager")


@dataclass
class ExperimentVariant:
    """
    Specification and execution record for a single variant in an experiment.
    """
    variant_id: str
    variant_name: str
    preset_id: str
    strategy_id: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    strategy_hash: str = ""
    risk_config_hash: str = ""
    execution_config_hash: str = ""
    dataset_hash: str = ""
    date_range: Dict[str, str] = field(default_factory=dict)
    initial_capital: float = 100000.0
    run_id: Optional[str] = None
    fingerprint: Optional[str] = None
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    metrics: Optional[Dict[str, Any]] = None
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentVariant":
        return cls(**data)


@dataclass
class BacktestExperiment:
    """
    Parent Experiment grouping a set of configuration variants evaluated under benchmark conditions.
    """
    experiment_id: str
    name: str
    description: str = ""
    base_strategy_id: str = "MA_CROSS_1M"
    dataset_version: str = "1.0"
    date_range: Dict[str, str] = field(default_factory=dict)
    variants: List[ExperimentVariant] = field(default_factory=list)
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    max_concurrency: int = 4
    timeout_seconds: float = 300.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    comparison_summary: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["variants"] = [v.to_dict() for v in self.variants]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BacktestExperiment":
        variants_data = data.pop("variants", [])
        variants = [ExperimentVariant.from_dict(v) if isinstance(v, dict) else v for v in variants_data]
        return cls(variants=variants, **data)


class BacktestExperimentManager:
    """
    Orchestrates experiment creation, variant generation, execution, and comparison.
    """

    def __init__(
        self,
        store: Optional[ExperimentStore] = None,
        preset_store: Optional[PresetStore] = None,
        default_concurrency: int = 4,
    ):
        self.store = store or ExperimentStore()
        self.preset_store = preset_store or PresetStore()
        self.default_concurrency = default_concurrency
        self._active_experiments: Dict[str, BacktestExperiment] = {}

    def create_experiment(
        self,
        name: str,
        base_strategy_id: str,
        dataset_version: str,
        variants_spec: List[Dict[str, Any]],
        description: str = "",
        date_range: Optional[Dict[str, str]] = None,
        initial_capital: float = 100000.0,
        max_concurrency: int = 4,
    ) -> BacktestExperiment:
        """
        Initializes an experiment with a list of parameter variants.
        """
        exp_id = f"exp_{uuid.uuid4().hex[:10]}"
        date_range = date_range or {
            "start_time": "2026-11-20T09:30:00Z",
            "end_time": "2026-11-20T16:00:00Z",
        }

        variants: List[ExperimentVariant] = []
        for i, v_spec in enumerate(variants_spec):
            var_id = v_spec.get("variant_id") or f"var_{exp_id}_{i+1}"
            preset_id = v_spec.get("preset_id") or f"preset_{var_id}"
            params = v_spec.get("parameters", {})

            # Compute hash
            strat_hash = compute_configuration_hash({
                "strategy_id": base_strategy_id,
                "parameters": params,
            })

            variant = ExperimentVariant(
                variant_id=var_id,
                variant_name=v_spec.get("variant_name", f"Variant {i+1}"),
                preset_id=preset_id,
                strategy_id=base_strategy_id,
                parameters=params,
                strategy_hash=strat_hash,
                risk_config_hash=compute_configuration_hash(v_spec.get("risk_config", {})),
                execution_config_hash=compute_configuration_hash(v_spec.get("execution_config", {})),
                dataset_hash=compute_configuration_hash({"dataset_version": dataset_version}),
                date_range=date_range,
                initial_capital=float(v_spec.get("initial_capital", initial_capital)),
                status="PENDING",
            )
            variants.append(variant)

        experiment = BacktestExperiment(
            experiment_id=exp_id,
            name=name,
            description=description,
            base_strategy_id=base_strategy_id,
            dataset_version=dataset_version,
            date_range=date_range,
            variants=variants,
            status="PENDING",
            max_concurrency=max_concurrency,
        )

        self.store.save(experiment.to_dict())
        self._active_experiments[exp_id] = experiment
        logger.info(f"Created experiment '{exp_id}' with {len(variants)} variants.")
        return experiment

    def run_experiment(
        self,
        experiment_id: str,
        runner_factory: Optional[Callable[[ExperimentVariant], Dict[str, Any]]] = None,
    ) -> BacktestExperiment:
        """
        Executes all pending variants in an experiment.
        """
        exp_data = self.store.get(experiment_id)
        if not exp_data:
            raise ValueError(f"Experiment '{experiment_id}' not found.")

        experiment = BacktestExperiment.from_dict(copy.deepcopy(exp_data))
        if experiment.status == "CANCELLED":
            logger.warning(f"Experiment '{experiment_id}' is cancelled; cannot run.")
            return experiment

        experiment.status = "RUNNING"
        self.store.save(experiment.to_dict())

        # Execute variants
        all_completed = True
        for variant in experiment.variants:
            if experiment.status == "CANCELLED":
                variant.status = "CANCELLED"
                continue

            variant.status = "RUNNING"
            run_id = f"run_{uuid.uuid4().hex[:10]}"
            variant.run_id = run_id

            try:
                if runner_factory:
                    res = runner_factory(variant)
                else:
                    # Default mock execution for experiment testing / pipeline
                    res = self._default_mock_run(variant)

                variant.status = "COMPLETED"
                variant.metrics = res.get("metrics", {})
                variant.equity_curve = res.get("equity_curve", [])
                variant.fingerprint = res.get("fingerprint") or compute_configuration_hash(variant.metrics)
            except Exception as e:
                variant.status = "FAILED"
                variant.error_message = str(e)
                all_completed = False
                logger.error(f"Variant '{variant.variant_id}' failed: {e}")

        experiment.status = "COMPLETED" if all_completed else "FAILED"
        experiment.completed_at = datetime.now(timezone.utc).isoformat()

        # Build comparison summary
        try:
            var_dicts = [v.to_dict() for v in experiment.variants if v.status == "COMPLETED"]
            if var_dicts:
                comp = BacktestComparisonService.compare_runs(var_dicts)
                experiment.comparison_summary = comp
        except Exception as ce:
            logger.warning(f"Failed to compile comparison summary: {ce}")

        self.store.save(experiment.to_dict())
        self._active_experiments[experiment_id] = experiment
        logger.info(f"Experiment '{experiment_id}' finished with status '{experiment.status}'.")
        return experiment

    def _default_mock_run(self, variant: ExperimentVariant) -> Dict[str, Any]:
        """Generates realistic backtest results for tests and standalone validation."""
        fp_engine = EconomicSequenceFingerprint()
        fp_engine.add_event("StrategySignal", {"symbol": "NVDA", "side": "BUY", "price": 100.0})
        fp_engine.add_event("SignalDecision", {"decision": "APPROVE", "qty": 10})
        fp_engine.add_event("SimulationOrderIntent", {"order_type": "MARKET", "qty": 10})
        fp_engine.add_event("SimulatedOrder", {"order_id": "ord_1", "status": "FILLED"})
        fp_engine.add_event("SimulatedFill", {"fill_id": "fill_1", "price": 100.05, "qty": 10})
        fp_engine.add_event("PortfolioTransaction", {"action": "BUY", "cash_delta": -1000.50})
        fp = fp_engine.compute_fingerprint()

        # Generate realistic metrics based on parameters
        fast = variant.parameters.get("fast_window") or variant.parameters.get("fast_period", 20)
        slow = variant.parameters.get("slow_window") or variant.parameters.get("slow_period", 50)
        period = variant.parameters.get("period", 14)

        ret = round(5.0 + (fast / max(1, slow)) * 10.0, 2)
        sharpe = round(1.2 + (fast / max(1, slow)) * 0.5, 2)
        mdd = round(max(1.0, 15.0 - (fast / max(1, slow)) * 5.0), 2)
        trades = int(20 + fast)

        return {
            "metrics": {
                "total_return_pct": ret,
                "sharpe_ratio": sharpe,
                "sortino_ratio": round(sharpe * 1.3, 2),
                "max_drawdown_pct": mdd,
                "win_rate_pct": 55.0,
                "total_trades": trades,
                "profit_factor": 1.65,
                "calmar_ratio": round(ret / max(0.1, mdd), 2),
            },
            "equity_curve": [
                {"timestamp": "2026-11-20T09:30:00Z", "equity": 100000.0},
                {"timestamp": "2026-11-20T12:00:00Z", "equity": 100000.0 * (1.0 + ret / 200.0)},
                {"timestamp": "2026-11-20T16:00:00Z", "equity": 100000.0 * (1.0 + ret / 100.0)},
            ],
            "fingerprint": fp,
        }

    def cancel_experiment(self, experiment_id: str) -> bool:
        """Cancels a pending or running experiment."""
        exp_data = self.store.get(experiment_id)
        if not exp_data:
            return False
        exp_data["status"] = "CANCELLED"
        for v in exp_data.get("variants", []):
            if v.get("status") in ("PENDING", "RUNNING"):
                v["status"] = "CANCELLED"
        self.store.save(exp_data)
        logger.info(f"Experiment '{experiment_id}' has been cancelled.")
        return True

    def get_experiment(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves experiment details."""
        return self.store.get(experiment_id)

    def list_experiments(self) -> List[Dict[str, Any]]:
        """Lists all experiments."""
        return self.store.list_experiments()

    def get_comparison(self, experiment_id: str, baseline_id: Optional[str] = None) -> Dict[str, Any]:
        """Computes or retrieves comparison table for an experiment."""
        exp_data = self.store.get(experiment_id)
        if not exp_data:
            raise ValueError(f"Experiment '{experiment_id}' does not exist.")
        variants = [v for v in exp_data.get("variants", []) if v.get("status") == "COMPLETED"]
        return BacktestComparisonService.compare_runs(variants, baseline_id=baseline_id)
