"""
libs/bot/strategy_config/registry.py — Strategy Configuration Registry (GĐ38)
Maintains declarative StrategyDefinitions, schemas, indicators, and metadata for AlgoTrading V2.0.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import logging

from libs.bot.strategy_config.schemas import ParameterSchema, StrategySchemaValidator, ValidationResult

logger = logging.getLogger("strategy-config-registry")


@dataclass
class StrategyDefinition:
    """
    Formal metadata and configuration specification of a trading strategy.
    """
    strategy_id: str
    strategy_version: str
    strategy_name: str
    strategy_type: str  # MOMENTUM, MEAN_REVERSION, STAT_ARB, etc.
    parameter_schema: Dict[str, ParameterSchema]
    supported_timeframes: List[str] = field(default_factory=lambda: ["1m"])
    supported_asset_classes: List[str] = field(default_factory=lambda: ["US_EQUITY", "CRYPTO"])
    required_indicators: List[str] = field(default_factory=list)
    warmup_requirements: int = 50
    signal_types: List[str] = field(default_factory=lambda: ["BUY", "SELL", "HOLD"])
    description: str = ""
    enabled: bool = True

    def validate_parameters(self, params: Dict[str, Any], allow_unknown: bool = False) -> ValidationResult:
        """Validates runtime parameters against this strategy definition's schema."""
        return StrategySchemaValidator.validate(
            strategy_id=self.strategy_id,
            schemas=self.parameter_schema,
            params=params,
            allow_unknown=allow_unknown,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes definition to dictionary representation."""
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_name": self.strategy_name,
            "strategy_type": self.strategy_type,
            "supported_timeframes": self.supported_timeframes,
            "supported_asset_classes": self.supported_asset_classes,
            "required_indicators": self.required_indicators,
            "warmup_requirements": self.warmup_requirements,
            "signal_types": self.signal_types,
            "description": self.description,
            "enabled": self.enabled,
            "parameter_schema": {
                name: {
                    "name": s.name,
                    "data_type": s.data_type,
                    "required": s.required,
                    "default": s.default,
                    "minimum": s.minimum,
                    "maximum": s.maximum,
                    "permitted_values": s.permitted_values,
                    "units": s.units,
                    "description": s.description,
                }
                for name, s in self.parameter_schema.items()
            },
        }


class StrategyConfigurationRegistry:
    """
    Central registry for declarative strategy configurations and parameter schemas.
    """

    def __init__(self):
        self._registry: Dict[str, StrategyDefinition] = {}
        self._register_builtins()

    def _register_builtins(self):
        """Registers built-in AlgoTrading V2.0 strategies."""
        # 1. Moving Average Crossover 1m
        ma_cross = StrategyDefinition(
            strategy_id="MA_CROSS_1M",
            strategy_version="1.0.0",
            strategy_name="Moving Average Crossover 1-Minute",
            strategy_type="MOMENTUM",
            parameter_schema={
                "fast_window": ParameterSchema(
                    name="fast_window",
                    data_type="int",
                    required=True,
                    default=20,
                    minimum=1,
                    maximum=500,
                    units="bars",
                    description="Lookback period for the fast moving average",
                ),
                "slow_window": ParameterSchema(
                    name="slow_window",
                    data_type="int",
                    required=True,
                    default=50,
                    minimum=2,
                    maximum=2000,
                    units="bars",
                    description="Lookback period for the slow moving average",
                ),
                "indicator_type": ParameterSchema(
                    name="indicator_type",
                    data_type="str",
                    required=False,
                    default="SMA",
                    permitted_values=["SMA", "EMA"],
                    description="Type of moving average calculation",
                ),
                "emit_hold": ParameterSchema(
                    name="emit_hold",
                    data_type="bool",
                    required=False,
                    default=False,
                    description="Whether to emit HOLD signals when no crossover occurs",
                ),
                "require_final": ParameterSchema(
                    name="require_final",
                    data_type="bool",
                    required=False,
                    default=True,
                    description="Only evaluate strategy on finalized 1m bars",
                ),
            },
            supported_timeframes=["1m"],
            supported_asset_classes=["US_EQUITY", "CRYPTO"],
            required_indicators=["SMA", "EMA"],
            warmup_requirements=50,
            signal_types=["BUY", "SELL", "HOLD"],
            description="Classic dual moving average crossover strategy on 1-minute bars.",
        )
        self.register(ma_cross)

        # 2. RSI Mean Reversion 1m
        rsi_1m = StrategyDefinition(
            strategy_id="RSI_1M",
            strategy_version="1.0.0",
            strategy_name="Relative Strength Index 1-Minute",
            strategy_type="MEAN_REVERSION",
            parameter_schema={
                "period": ParameterSchema(
                    name="period",
                    data_type="int",
                    required=True,
                    default=14,
                    minimum=2,
                    maximum=200,
                    units="bars",
                    description="Lookback period for RSI computation",
                ),
                "oversold_threshold": ParameterSchema(
                    name="oversold_threshold",
                    data_type="float",
                    required=True,
                    default=30.0,
                    minimum=0.0,
                    maximum=100.0,
                    units="index",
                    description="Oversold boundary below which a BUY signal is triggered",
                ),
                "overbought_threshold": ParameterSchema(
                    name="overbought_threshold",
                    data_type="float",
                    required=True,
                    default=70.0,
                    minimum=0.0,
                    maximum=100.0,
                    units="index",
                    description="Overbought boundary above which a SELL signal is triggered",
                ),
                "method": ParameterSchema(
                    name="method",
                    data_type="str",
                    required=False,
                    default="WILDER",
                    permitted_values=["WILDER", "SIMPLE_ROLLING"],
                    description="Smoothing algorithm for RSI average gains/losses",
                ),
                "require_final": ParameterSchema(
                    name="require_final",
                    data_type="bool",
                    required=False,
                    default=True,
                    description="Only evaluate strategy on finalized 1m bars",
                ),
            },
            supported_timeframes=["1m"],
            supported_asset_classes=["US_EQUITY", "CRYPTO"],
            required_indicators=["RSI"],
            warmup_requirements=14,
            signal_types=["BUY", "SELL", "HOLD"],
            description="Mean reversion strategy triggering on RSI oversold and overbought extremes.",
        )
        self.register(rsi_1m)

    def register(self, definition: StrategyDefinition) -> None:
        """Registers or replaces a strategy definition."""
        self._registry[definition.strategy_id] = definition
        logger.info(f"Registered strategy definition: {definition.strategy_id} (v{definition.strategy_version})")

    def get(self, strategy_id: str) -> Optional[StrategyDefinition]:
        """Retrieves a strategy definition by ID."""
        return self._registry.get(strategy_id)

    def list_strategies(self) -> List[Dict[str, Any]]:
        """Lists all registered strategy definitions."""
        return [defn.to_dict() for defn in self._registry.values()]

    def validate_parameters(
        self, strategy_id: str, params: Dict[str, Any], allow_unknown: bool = False
    ) -> ValidationResult:
        """Validates parameters for the given strategy ID."""
        defn = self.get(strategy_id)
        if not defn:
            return ValidationResult(
                is_valid=False,
                errors=[f"Strategy '{strategy_id}' is not registered in StrategyConfigurationRegistry."],
            )
        return defn.validate_parameters(params, allow_unknown=allow_unknown)
