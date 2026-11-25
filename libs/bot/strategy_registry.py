"""
libs/bot/strategy_registry.py — Strategy Plugin Registry (GĐ31)
Provides central registration, versioning, configuration validation,
and instantiation for trading strategy plugins.
Security: Rejects loading or executing arbitrary untrusted external code.
"""

from typing import Dict, Any, Type, Optional, List, Tuple
import logging

from libs.bot.strategies.base import BaseStrategy

logger = logging.getLogger("strategy-registry")


class StrategyRegistryError(Exception):
    """Raised when strategy registration, lookup, or validation fails."""
    pass


class StrategyRegistry:
    """
    Central repository for all valid trading strategy plugins.
    Ensures explicit version tracking and configuration validation.
    """

    def __init__(self):
        # key: f"{strategy_id}:{version}" -> strategy class
        self._registry: Dict[str, Type[BaseStrategy]] = {}
        # strategy_id -> list of available versions
        self._versions: Dict[str, List[str]] = {}

    def register(self, strategy_cls: Type[BaseStrategy], default_version: bool = True) -> None:
        """Registers a BaseStrategy class."""
        if not issubclass(strategy_cls, BaseStrategy):
            raise StrategyRegistryError(f"Class {strategy_cls} must subclass BaseStrategy")

        # Create temporary instance with defaults to inspect identity
        try:
            temp = strategy_cls()
            strat_id = temp.strategy_id
            version = temp.strategy_version
        except Exception as e:
            raise StrategyRegistryError(f"Cannot inspect default strategy instance for {strategy_cls}: {e}")

        key = f"{strat_id}:{version}"
        self._registry[key] = strategy_cls

        if strat_id not in self._versions:
            self._versions[strat_id] = []
        if version not in self._versions[strat_id]:
            self._versions[strat_id].append(version)

        logger.info("Registered strategy plugin: %s (v%s)", strat_id, version)

    def get_class(self, strategy_id: str, version: Optional[str] = None) -> Type[BaseStrategy]:
        """Retrieves registered strategy class by ID and optional version."""
        if strategy_id not in self._versions or not self._versions[strategy_id]:
            raise StrategyRegistryError(f"Strategy '{strategy_id}' is not registered")

        ver = version or self._versions[strategy_id][-1]
        key = f"{strategy_id}:{ver}"
        if key not in self._registry:
            raise StrategyRegistryError(f"Strategy '{strategy_id}' version '{ver}' not found")

        return self._registry[key]

    def validate_configuration(self, strategy_id: str, config: Dict[str, Any], version: Optional[str] = None) -> Tuple[bool, List[str]]:
        """Validates configuration parameters against strategy schema."""
        errors: List[str] = []
        strat_cls = self.get_class(strategy_id, version)
        temp = strat_cls()
        schema = temp.configuration_schema

        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required parameter '{field}'")

        properties = schema.get("properties", {})
        for k, v in config.items():
            if k in properties:
                prop = properties[k]
                expected_type = prop.get("type")
                if expected_type == "integer" and not isinstance(v, int):
                    errors.append(f"Parameter '{k}' must be integer, got {type(v).__name__}")
                elif expected_type == "number" and not isinstance(v, (int, float)):
                    errors.append(f"Parameter '{k}' must be number, got {type(v).__name__}")
                elif expected_type == "boolean" and not isinstance(v, bool):
                    errors.append(f"Parameter '{k}' must be boolean, got {type(v).__name__}")

                if "minimum" in prop and isinstance(v, (int, float)) and v < prop["minimum"]:
                    errors.append(f"Parameter '{k}' ({v}) less than minimum ({prop['minimum']})")
                if "maximum" in prop and isinstance(v, (int, float)) and v > prop["maximum"]:
                    errors.append(f"Parameter '{k}' ({v}) exceeds maximum ({prop['maximum']})")
                if "enum" in prop and v not in prop["enum"]:
                    errors.append(f"Parameter '{k}' value '{v}' not in allowed choices {prop['enum']}")

        return len(errors) == 0, errors

    def instantiate(
        self,
        strategy_id: str,
        configuration: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
    ) -> BaseStrategy:
        """Instantiates a validated strategy instance."""
        strat_cls = self.get_class(strategy_id, version)
        cfg = configuration or {}
        is_valid, errors = self.validate_configuration(strategy_id, cfg, version)
        if not is_valid:
            raise StrategyRegistryError(f"Configuration validation failed for '{strategy_id}': {errors}")

        return strat_cls(**cfg)

    # Alias for convenience
    create_instance = instantiate

    def list_strategies(self) -> List[Dict[str, Any]]:
        """Returns catalogue of all registered strategies."""
        catalogue = []
        for strat_id, vers in self._versions.items():
            for v in vers:
                cls_ = self._registry[f"{strat_id}:{v}"]
                inst = cls_()
                catalogue.append({
                    "strategy_id": strat_id,
                    "strategy_name": inst.strategy_name,
                    "version": v,
                    "required_timeframe": inst.required_timeframe,
                    "required_indicators": inst.required_indicators,
                    "required_warmup_bars": inst.required_warmup_bars,
                    "schema": inst.configuration_schema,
                })
        return catalogue


# Global default registry populated with core strategies
default_registry = StrategyRegistry()
from libs.bot.strategies.ma_crossover import MovingAverageCrossoverStrategy
from libs.bot.strategies.rsi_strategy import RSIStrategy
from libs.bot.strategies.v1_adapter import V1StrategyAdapter

default_registry.register(MovingAverageCrossoverStrategy)
default_registry.register(RSIStrategy)
default_registry.register(V1StrategyAdapter)
