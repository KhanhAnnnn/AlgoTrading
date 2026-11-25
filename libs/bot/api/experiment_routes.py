"""
libs/bot/api/experiment_routes.py — Strategy Configuration & Experiment API Endpoints (GĐ38)
Provides REST endpoints for Strategy Registry, Schemas, Presets, Experiments, and Comparison.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status

from libs.bot.api.auth import verify_api_key
from libs.bot.strategy_config.registry import StrategyConfigurationRegistry
from libs.bot.strategy_config.presets import (
    PresetStore,
    StrategyPreset,
    PresetImmutableError,
    PresetNotFoundError,
)
from libs.bot.strategy_config.schemas import ValidationError
from libs.bot.experiments.manager import (
    BacktestExperimentManager,
    BacktestExperiment,
    ExperimentVariant,
)
from libs.bot.experiments.store import ExperimentStore
from libs.bot.experiments.comparison import BacktestComparisonService

logger = logging.getLogger("experiment-api")

router = APIRouter(prefix="/api/v2", tags=["V2 Strategy Config & Experiments"])

# Global singletons
strategy_registry = StrategyConfigurationRegistry()
preset_store = PresetStore()
experiment_store = ExperimentStore()
experiment_manager = BacktestExperimentManager(store=experiment_store, preset_store=preset_store)


# --- Schemas ---

class CreatePresetRequest(BaseModel):
    preset_id: str = Field(description="Unique identifier for the preset")
    preset_name: str = Field(description="Human readable name for the preset")
    strategy_id: str = Field(default="MA_CROSS_1M", description="Associated strategy ID")
    strategy_version: str = Field(default="1.0.0", description="Strategy version string")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")
    risk_config_reference: Optional[str] = None
    execution_config_reference: Optional[str] = None


class ClonePresetRequest(BaseModel):
    new_preset_id: str = Field(description="Unique ID for cloned preset")
    new_preset_name: str = Field(description="Name for cloned preset")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Updated parameters")


class VariantSpec(BaseModel):
    variant_id: Optional[str] = None
    variant_name: Optional[str] = None
    preset_id: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    initial_capital: Optional[float] = 100000.0


class CreateExperimentRequest(BaseModel):
    name: str = Field(description="Experiment title")
    description: str = Field(default="", description="Detailed experiment description")
    base_strategy_id: str = Field(default="MA_CROSS_1M", description="Strategy being evaluated")
    dataset_version: str = Field(default="1.0", description="Dataset benchmark version")
    date_range: Optional[Dict[str, str]] = None
    initial_capital: float = Field(default=100000.0, ge=100.0)
    max_concurrency: int = Field(default=4, ge=1, le=16)
    variants: List[VariantSpec] = Field(description="List of configuration variants to evaluate")


# --- Strategy Endpoints ---

@router.get("/strategies")
def list_strategies(api_key: str = Depends(verify_api_key)):
    """Lists all registered strategies with full metadata and parameter schemas."""
    return {"strategies": strategy_registry.list_strategies()}


@router.get("/strategies/{strategy_id}")
def get_strategy(strategy_id: str, api_key: str = Depends(verify_api_key)):
    """Retrieves definition and schema for a specific strategy."""
    defn = strategy_registry.get(strategy_id)
    if not defn:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found.")
    return defn.to_dict()


# --- Preset Endpoints ---

@router.get("/strategy-presets")
def list_presets(
    strategy_id: Optional[str] = Query(None, description="Filter by strategy_id"),
    api_key: str = Depends(verify_api_key),
):
    """Lists all stored strategy presets."""
    presets = preset_store.list_presets(strategy_id=strategy_id)
    return {"presets": [p.to_dict() for p in presets]}


@router.post("/strategy-presets", status_code=status.HTTP_201_CREATED)
def create_preset(req: CreatePresetRequest, api_key: str = Depends(verify_api_key)):
    """Creates a new immutable strategy preset with strict schema validation."""
    # 1. Validate parameters against registry
    val_res = strategy_registry.validate_parameters(req.strategy_id, req.parameters)
    if not val_res.is_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Parameter validation failed: {'; '.join(val_res.errors)}",
        )

    preset = StrategyPreset(
        preset_id=req.preset_id,
        preset_name=req.preset_name,
        strategy_id=req.strategy_id,
        strategy_version=req.strategy_version,
        parameters=val_res.normalized_params,
        risk_config_reference=req.risk_config_reference,
        execution_config_reference=req.execution_config_reference,
        is_immutable=True,
    )
    try:
        preset_store.save(preset)
    except PresetImmutableError as pie:
        raise HTTPException(status_code=409, detail=str(pie))

    return preset.to_dict()


@router.get("/strategy-presets/{preset_id}")
def get_preset(preset_id: str, api_key: str = Depends(verify_api_key)):
    """Retrieves an existing preset by ID."""
    try:
        preset = preset_store.get(preset_id)
        return preset.to_dict()
    except PresetNotFoundError:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found.")


@router.post("/strategy-presets/{preset_id}/clone", status_code=status.HTTP_201_CREATED)
def clone_preset(preset_id: str, req: ClonePresetRequest, api_key: str = Depends(verify_api_key)):
    """Clones an existing preset with optional modified parameters, producing a new version/ID."""
    try:
        source = preset_store.get(preset_id)
    except PresetNotFoundError:
        raise HTTPException(status_code=404, detail=f"Source preset '{preset_id}' not found.")

    merged_params = dict(source.parameters)
    if req.parameters:
        merged_params.update(req.parameters)

    val_res = strategy_registry.validate_parameters(source.strategy_id, merged_params)
    if not val_res.is_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Parameter validation failed for cloned preset: {'; '.join(val_res.errors)}",
        )

    try:
        cloned = preset_store.clone_preset(
            source_preset_id=preset_id,
            new_preset_id=req.new_preset_id,
            new_preset_name=req.new_preset_name,
            new_parameters=val_res.normalized_params,
        )
        return cloned.to_dict()
    except PresetImmutableError as pie:
        raise HTTPException(status_code=409, detail=str(pie))


# --- Experiment Endpoints ---

@router.get("/experiments")
def list_experiments(api_key: str = Depends(verify_api_key)):
    """Lists all backtest experiments."""
    return {"experiments": experiment_manager.list_experiments()}


@router.post("/experiments", status_code=status.HTTP_201_CREATED)
def create_experiment(req: CreateExperimentRequest, api_key: str = Depends(verify_api_key)):
    """Creates a new backtest experiment with parameter variants."""
    variants_spec = [v.model_dump() for v in req.variants]
    exp = experiment_manager.create_experiment(
        name=req.name,
        description=req.description,
        base_strategy_id=req.base_strategy_id,
        dataset_version=req.dataset_version,
        variants_spec=variants_spec,
        date_range=req.date_range,
        initial_capital=req.initial_capital,
        max_concurrency=req.max_concurrency,
    )
    return exp.to_dict()


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str, api_key: str = Depends(verify_api_key)):
    """Retrieves full details of an experiment and its variants."""
    exp = experiment_manager.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found.")
    return exp


@router.post("/experiments/{experiment_id}/run")
def run_experiment(experiment_id: str, api_key: str = Depends(verify_api_key)):
    """Executes the variants in an experiment."""
    try:
        exp = experiment_manager.run_experiment(experiment_id)
        return exp.to_dict()
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))


@router.get("/experiments/{experiment_id}/comparison")
def get_experiment_comparison(
    experiment_id: str,
    baseline_id: Optional[str] = Query(None, description="Optional baseline variant_id"),
    api_key: str = Depends(verify_api_key),
):
    """Retrieves multi-run KPI comparison table, deltas, and comparability validation."""
    try:
        return experiment_manager.get_comparison(experiment_id, baseline_id=baseline_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))


@router.post("/experiments/{experiment_id}/cancel")
def cancel_experiment(experiment_id: str, api_key: str = Depends(verify_api_key)):
    """Cancels a pending or running experiment."""
    success = experiment_manager.cancel_experiment(experiment_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found.")
    return {"status": "CANCELLED", "experiment_id": experiment_id}
