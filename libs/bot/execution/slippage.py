"""
libs/bot/execution/slippage.py — Slippage Models for Simulation Broker (GĐ33)
Implements Zero Slippage baseline, Fixed Basis Points (BPS), and Market Impact models.
Slippage is strictly adverse according to trade direction.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Any, Tuple
import hashlib
import json

from libs.bot.portfolio.accounting import to_decimal


class SlippageModel(ABC):
    """Abstract base class for simulation execution slippage models."""

    @abstractmethod
    def calculate_slippage(
        self,
        base_price: Decimal,
        side: str,
        quantity: Decimal,
        bar_volume: Decimal = Decimal("0.0"),
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculates execution price and slippage amount.
        Returns (executed_price, slippage_amount).
        """
        pass

    @abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """Returns model identifier, version, and parameters."""
        pass


class ZeroSlippageModel(SlippageModel):
    """Zero slippage baseline for benchmark comparisons."""

    def calculate_slippage(
        self,
        base_price: Decimal,
        side: str,
        quantity: Decimal,
        bar_volume: Decimal = Decimal("0.0"),
    ) -> Tuple[Decimal, Decimal]:
        p = to_decimal(base_price)
        return p, Decimal("0.0")

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "model_name": "ZERO_SLIPPAGE",
            "version": "1.0.0",
            "parameters": {},
        }


class FixedBpsSlippageModel(SlippageModel):
    """
    Fixed basis point slippage model.
    Adverse adjustment:
    BUY: Price increases by bps/10000.
    SELL: Price decreases by bps/10000.
    """

    def __init__(self, bps: float = 5.0):
        if bps < 0:
            raise ValueError(f"Slippage BPS cannot be negative: {bps}")
        self.bps = to_decimal(bps)

    def calculate_slippage(
        self,
        base_price: Decimal,
        side: str,
        quantity: Decimal,
        bar_volume: Decimal = Decimal("0.0"),
    ) -> Tuple[Decimal, Decimal]:
        p = to_decimal(base_price)
        if p <= Decimal("0.0"):
            raise ValueError(f"Base price must be positive, got {base_price}")

        slippage_pct = self.bps / Decimal("10000.0")
        slippage_amt = p * slippage_pct

        if side.upper() == "BUY":
            exec_price = p + slippage_amt
        elif side.upper() == "SELL":
            exec_price = p - slippage_amt
            if exec_price <= Decimal("0.0"):
                exec_price = p * Decimal("0.0001")  # Floor guard
        else:
            raise ValueError(f"Invalid order side: {side}")

        return exec_price, slippage_amt

    def get_metadata(self) -> Dict[str, Any]:
        params = {"bps": float(self.bps)}
        param_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
        return {
            "model_name": "FIXED_BPS",
            "version": "1.0.0",
            "parameters": params,
            "parameter_hash": param_hash,
        }


class ConfigurableImpactSlippageModel(SlippageModel):
    """
    Volume-participation impact slippage model.
    Slippage = BaseBps + (ImpactCoef * (Quantity / BarVolume)).
    """

    def __init__(self, base_bps: float = 2.0, impact_coefficient: float = 0.1):
        if base_bps < 0:
            raise ValueError(f"base_bps cannot be negative: {base_bps}")
        if impact_coefficient < 0:
            raise ValueError(f"impact_coefficient cannot be negative: {impact_coefficient}")
        self.base_bps = to_decimal(base_bps)
        self.impact_coef = to_decimal(impact_coefficient)

    def calculate_slippage(
        self,
        base_price: Decimal,
        side: str,
        quantity: Decimal,
        bar_volume: Decimal = Decimal("0.0"),
    ) -> Tuple[Decimal, Decimal]:
        p = to_decimal(base_price)
        q = to_decimal(quantity)
        v = to_decimal(bar_volume)

        if p <= Decimal("0.0"):
            raise ValueError(f"Base price must be positive, got {base_price}")

        participation_ratio = Decimal("0.0")
        if v > Decimal("0.0"):
            participation_ratio = min(Decimal("1.0"), q / v)

        effective_bps = self.base_bps + (self.impact_coef * participation_ratio * Decimal("100.0"))
        slippage_pct = effective_bps / Decimal("10000.0")
        slippage_amt = p * slippage_pct

        if side.upper() == "BUY":
            exec_price = p + slippage_amt
        elif side.upper() == "SELL":
            exec_price = max(Decimal("0.0001"), p - slippage_amt)
        else:
            raise ValueError(f"Invalid order side: {side}")

        return exec_price, slippage_amt

    def get_metadata(self) -> Dict[str, Any]:
        params = {
            "base_bps": float(self.base_bps),
            "impact_coefficient": float(self.impact_coef),
        }
        param_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
        return {
            "model_name": "CONFIGURABLE_IMPACT",
            "version": "1.0.0",
            "parameters": params,
            "parameter_hash": param_hash,
        }
