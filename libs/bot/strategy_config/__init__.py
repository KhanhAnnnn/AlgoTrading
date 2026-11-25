"""
libs/bot/strategy_config/__init__.py — Strategy Configuration, Versioning & Presets Package (GĐ38)
"""

from libs.bot.strategy_config.schemas import (
    ParameterSchema,
    StrategySchemaValidator,
    ValidationResult,
    ValidationError,
)
from libs.bot.strategy_config.registry import (
    StrategyDefinition,
    StrategyConfigurationRegistry,
)
from libs.bot.strategy_config.versioning import (
    canonical_serialize,
    compute_configuration_hash,
)
from libs.bot.strategy_config.presets import (
    StrategyPreset,
    PresetStore,
    PresetImmutableError,
    PresetNotFoundError,
)

__all__ = [
    "ParameterSchema",
    "StrategySchemaValidator",
    "ValidationResult",
    "ValidationError",
    "StrategyDefinition",
    "StrategyConfigurationRegistry",
    "canonical_serialize",
    "compute_configuration_hash",
    "StrategyPreset",
    "PresetStore",
    "PresetImmutableError",
    "PresetNotFoundError",
]
