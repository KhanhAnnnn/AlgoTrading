"""
libs/bot/execution/fees.py — Commission & Fee Models (GĐ33)
Implements Zero Fee baseline and asset-class specific fee schedules using Decimal math.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from dataclasses import dataclass
from typing import Dict, Any

from libs.bot.portfolio.accounting import to_decimal, quantize_currency


@dataclass
class FeeResult:
    """Breakdown of calculated commission and exchange fees."""
    fee_amount: Decimal
    fee_currency: str = "USD"
    calculation_method: str = "PER_SHARE"
    model_version: str = "1.0.0"
    metadata: Dict[str, Any] = None


class FeeModel(ABC):
    """Abstract base class for fee calculation models."""

    @abstractmethod
    def calculate_fee(
        self,
        symbol: str,
        asset_class: str,
        side: str,
        quantity: Decimal,
        fill_price: Decimal,
    ) -> FeeResult:
        """Calculates total commission and transaction fees."""
        pass


class ZeroFeeModel(FeeModel):
    """Zero fee baseline for friction-free simulation comparison."""

    def calculate_fee(
        self,
        symbol: str,
        asset_class: str,
        side: str,
        quantity: Decimal,
        fill_price: Decimal,
    ) -> FeeResult:
        return FeeResult(
            fee_amount=Decimal("0.00"),
            fee_currency="USD",
            calculation_method="ZERO_FEE",
            model_version="1.0.0",
            metadata={"description": "Zero fee baseline model"},
        )


class ConfigurableFeeModel(FeeModel):
    """
    Asset-class differentiated fee model.
    STOCKS: Per-share fee with minimum order commission.
    CRYPTO: Basis point fee on total notional value.
    """

    def __init__(
        self,
        stocks_per_share: float = 0.005,
        stocks_min_commission: float = 1.00,
        crypto_bps: float = 10.0,  # 0.10% maker/taker estimate
    ):
        self.stocks_per_share = to_decimal(stocks_per_share)
        self.stocks_min_commission = to_decimal(stocks_min_commission)
        self.crypto_bps = to_decimal(crypto_bps)

    def calculate_fee(
        self,
        symbol: str,
        asset_class: str,
        side: str,
        quantity: Decimal,
        fill_price: Decimal,
    ) -> FeeResult:
        q = to_decimal(quantity)
        p = to_decimal(fill_price)
        notional = q * p

        is_crypto = (
            asset_class.upper() == "CRYPTO"
            or "BTC" in symbol
            or "ETH" in symbol
            or "/" in symbol
        )

        if is_crypto:
            # Notional BPS
            fee_pct = self.crypto_bps / Decimal("10000.0")
            raw_fee = notional * fee_pct
            fee_amount = quantize_currency(raw_fee)
            return FeeResult(
                fee_amount=fee_amount,
                fee_currency="USD",
                calculation_method="NOTIONAL_BPS",
                model_version="1.0.0",
                metadata={
                    "crypto_bps": float(self.crypto_bps),
                    "notional": float(notional),
                },
            )
        else:
            # Stocks: per-share with minimum
            raw_fee = q * self.stocks_per_share
            fee_amount = max(self.stocks_min_commission, quantize_currency(raw_fee))
            return FeeResult(
                fee_amount=fee_amount,
                fee_currency="USD",
                calculation_method="PER_SHARE_WITH_MINIMUM",
                model_version="1.0.0",
                metadata={
                    "per_share": float(self.stocks_per_share),
                    "min_commission": float(self.stocks_min_commission),
                },
            )
