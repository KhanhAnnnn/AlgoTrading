"""
libs/bot/strategy_config/schemas.py — Parameter Schemas & Strict Validation Engine (GĐ38)
Provides typed parameter definitions, boundary checks, and cross-parameter validation
for AlgoTrading V2.0 strategies (MA_CROSS_1M, RSI_1M).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
import logging

logger = logging.getLogger("strategy-schemas")


class ValidationError(Exception):
    """Raised when strategy parameters violate schema constraints."""
    pass


@dataclass
class ParameterSchema:
    """
    Metadata specification for a single strategy parameter.
    """
    name: str
    data_type: str  # "int", "float", "str", "bool", "list"
    required: bool = True
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    permitted_values: Optional[List[Any]] = None
    dependencies: Optional[Dict[str, Any]] = None
    units: Optional[str] = None
    description: Optional[str] = None

    def validate_value(self, val: Any) -> Any:
        """Validates and coerces a single parameter value."""
        if val is None:
            if self.required:
                raise ValidationError(f"Parameter '{self.name}' is required but was None or missing.")
            return self.default

        # Type checking / coercion
        if self.data_type == "int":
            if not isinstance(val, int) or isinstance(val, bool):
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    raise ValidationError(f"Parameter '{self.name}' must be an integer, got {type(val).__name__} ({val}).")
        elif self.data_type == "float":
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    raise ValidationError(f"Parameter '{self.name}' must be a float, got {type(val).__name__} ({val}).")
            val = float(val)
        elif self.data_type == "bool":
            if not isinstance(val, bool):
                if str(val).lower() in ("true", "1"):
                    val = True
                elif str(val).lower() in ("false", "0"):
                    val = False
                else:
                    raise ValidationError(f"Parameter '{self.name}' must be a boolean, got {type(val).__name__} ({val}).")
        elif self.data_type == "str":
            if not isinstance(val, str):
                val = str(val)

        # Bounds checking
        if self.minimum is not None and val < self.minimum:
            raise ValidationError(
                f"Parameter '{self.name}' value {val} is below minimum allowed {self.minimum}."
            )
        if self.maximum is not None and val > self.maximum:
            raise ValidationError(
                f"Parameter '{self.name}' value {val} exceeds maximum allowed {self.maximum}."
            )

        # Permitted values
        if self.permitted_values is not None and val not in self.permitted_values:
            raise ValidationError(
                f"Parameter '{self.name}' value '{val}' is not in permitted values: {self.permitted_values}."
            )

        return val


@dataclass
class ValidationResult:
    """Encapsulates the result of strategy parameter validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    normalized_params: Dict[str, Any] = field(default_factory=dict)


class StrategySchemaValidator:
    """
    Enforces parameter schema conformance and cross-parameter validation constraints.
    Rejects undeclared parameters (strict mode).
    """

    @staticmethod
    def validate(
        strategy_id: str,
        schemas: Dict[str, ParameterSchema],
        params: Dict[str, Any],
        allow_unknown: bool = False,
    ) -> ValidationResult:
        errors: List[str] = []
        normalized: Dict[str, Any] = {}

        # 1. Check for unknown/undeclared parameters
        if not allow_unknown:
            declared_names = set(schemas.keys())
            # Also allow recognized aliases
            aliases: Dict[str, str] = {}
            if strategy_id == "MA_CROSS_1M":
                aliases = {"fast_period": "fast_window", "slow_period": "slow_window"}
            elif strategy_id == "RSI_1M":
                aliases = {"oversold": "oversold_threshold", "overbought": "overbought_threshold"}

            all_known = declared_names.union(aliases.keys())
            for param_name in params.keys():
                if param_name not in all_known:
                    errors.append(f"Undeclared parameter '{param_name}' is not permitted for strategy '{strategy_id}'.")

        # Normalize aliases first
        resolved_params = dict(params)
        if strategy_id == "MA_CROSS_1M":
            if "fast_period" in resolved_params and "fast_window" not in resolved_params:
                resolved_params["fast_window"] = resolved_params["fast_period"]
            if "slow_period" in resolved_params and "slow_window" not in resolved_params:
                resolved_params["slow_window"] = resolved_params["slow_period"]
        elif strategy_id == "RSI_1M":
            if "oversold" in resolved_params and "oversold_threshold" not in resolved_params:
                resolved_params["oversold_threshold"] = resolved_params["oversold"]
            if "overbought" in resolved_params and "overbought_threshold" not in resolved_params:
                resolved_params["overbought_threshold"] = resolved_params["overbought"]

        # 2. Individual parameter validation
        for name, schema in schemas.items():
            raw_val = resolved_params.get(name)
            if raw_val is None:
                if schema.required and schema.default is None:
                    errors.append(f"Required parameter '{name}' is missing.")
                    continue
                raw_val = schema.default

            try:
                validated_val = schema.validate_value(raw_val)
                normalized[name] = validated_val
            except ValidationError as ve:
                errors.append(str(ve))

        # 3. Cross-parameter constraints
        if not errors:
            if strategy_id == "MA_CROSS_1M":
                fast = normalized.get("fast_window", 20)
                slow = normalized.get("slow_window", 50)
                if fast >= slow:
                    errors.append(
                        f"MA_CROSS constraint violated: fast_window ({fast}) must be strictly less than slow_window ({slow})."
                    )
            elif strategy_id == "RSI_1M":
                oversold = normalized.get("oversold_threshold", 30.0)
                overbought = normalized.get("overbought_threshold", 70.0)
                if not (0.0 <= oversold < overbought <= 100.0):
                    errors.append(
                        f"RSI constraint violated: must satisfy 0 <= oversold ({oversold}) < overbought ({overbought}) <= 100."
                    )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            normalized_params=normalized if len(errors) == 0 else {},
        )
