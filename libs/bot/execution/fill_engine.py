"""
libs/bot/execution/fill_engine.py — 1-Minute Bar Execution & Fill Engine (GĐ33)
Simulates order fills on finalized 1m OHLCV bars.
Prevents lookahead bias, enforces volume participation caps, and models
MARKET, LIMIT, STOP, STOP_LIMIT, and TRAILING_STOP execution.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
import uuid
import logging

from libs.bot.domain import SimulatedOrder, SimulatedFill, MarketDataEvent
from libs.bot.execution.slippage import SlippageModel, ZeroSlippageModel
from libs.bot.execution.fees import FeeModel, ZeroFeeModel
from libs.bot.portfolio.accounting import to_decimal, quantize_qty, quantize_currency

logger = logging.getLogger("fill-engine")


class FillEngine:
    """
    Evaluates order execution conditions against finalized 1-minute bars.
    Guarantees zero look-ahead bias and deterministic execution logic.
    """

    def __init__(
        self,
        slippage_model: Optional[SlippageModel] = None,
        fee_model: Optional[FeeModel] = None,
        max_participation_rate: float = 0.10,  # Max 10% bar volume per order/bar
    ):
        self.slippage_model = slippage_model or ZeroSlippageModel()
        self.fee_model = fee_model or ZeroFeeModel()
        self.max_participation_rate = to_decimal(max_participation_rate)
        # Tracks volume consumed per bar to share volume across competing orders: bar_key -> consumed_qty
        self._bar_consumed_volume: Dict[str, Decimal] = {}

    def evaluate_order(
        self,
        order: SimulatedOrder,
        bar: MarketDataEvent,
    ) -> Optional[SimulatedFill]:
        """
        Evaluates an active order against a finalized 1m bar.
        Returns SimulatedFill if execution conditions are met, otherwise None.
        """
        # 1. Bar Validation
        if not bar.is_final:
            logger.debug(f"Skipping execution: bar {bar.bar_key} is not final")
            return None

        # 2. Anti-Lookahead Guard: Order cannot execute on its own source signal bar
        if order.source_bar_key and order.source_bar_key == bar.bar_key:
            logger.debug(f"Lookahead prevention: Order {order.simulated_order_id} cannot execute on source bar {bar.bar_key}")
            return None

        # 3. Volume Check: Zero volume bars produce zero fills
        bar_vol = to_decimal(bar.volume)
        if bar_vol <= Decimal("0.0"):
            return None

        # Calculate remaining allowable volume in this bar
        bar_key = bar.bar_key
        consumed_so_far = self._bar_consumed_volume.get(bar_key, Decimal("0.0"))
        max_allowable_vol = bar_vol * self.max_participation_rate
        available_vol = max(Decimal("0.0"), max_allowable_vol - consumed_so_far)

        if available_vol <= Decimal("0.0"):
            return None

        # Order quantity to fill
        rem_qty = to_decimal(order.remaining_quantity)
        if rem_qty <= Decimal("0.0"):
            return None

        fill_qty = min(rem_qty, available_vol)
        # Quantize fill quantity according to asset precision (e.g. 4 decimals for crypto, 2 for stocks)
        precision = 4 if ("BTC" in order.symbol or "ETH" in order.symbol or "/" in order.symbol) else 2
        fill_qty = quantize_qty(fill_qty, decimals=precision)

        if fill_qty <= Decimal("0.0"):
            return None

        # 4. Evaluate Order Types
        o_type = order.order_type.upper()
        fill_price: Optional[Decimal] = None
        slippage_amt: Decimal = Decimal("0.0")

        open_p = to_decimal(bar.open)
        high_p = to_decimal(bar.high)
        low_p = to_decimal(bar.low)
        close_p = to_decimal(bar.close)

        # -------------------------------------------------------------
        # MARKET ORDER
        # -------------------------------------------------------------
        if o_type == "MARKET":
            fill_price, slippage_amt = self.slippage_model.calculate_slippage(
                base_price=open_p,
                side=order.side,
                quantity=fill_qty,
                bar_volume=bar_vol,
            )

        # -------------------------------------------------------------
        # LIMIT ORDER
        # -------------------------------------------------------------
        elif o_type == "LIMIT":
            if order.limit_price is None:
                return None
            limit_p = to_decimal(order.limit_price)

            if order.side.upper() == "BUY":
                # Can buy if bar low reached or dropped below limit
                if low_p <= limit_p:
                    if open_p <= limit_p:
                        # Favorable gap down or open below limit
                        raw_p, slippage_amt = self.slippage_model.calculate_slippage(
                            base_price=open_p,
                            side="BUY",
                            quantity=fill_qty,
                            bar_volume=bar_vol,
                        )
                        fill_price = min(limit_p, raw_p)
                    else:
                        fill_price = limit_p
            elif order.side.upper() == "SELL":
                # Can sell if bar high reached or exceeded limit
                if high_p >= limit_p:
                    if open_p >= limit_p:
                        # Favorable gap up or open above limit
                        raw_p, slippage_amt = self.slippage_model.calculate_slippage(
                            base_price=open_p,
                            side="SELL",
                            quantity=fill_qty,
                            bar_volume=bar_vol,
                        )
                        fill_price = max(limit_p, raw_p)
                    else:
                        fill_price = limit_p

        # -------------------------------------------------------------
        # STOP ORDER
        # -------------------------------------------------------------
        elif o_type == "STOP":
            if order.stop_price is None:
                return None
            stop_p = to_decimal(order.stop_price)

            if order.side.upper() == "BUY":
                if high_p >= stop_p:
                    # Triggered! Gap up handling:
                    base_p = open_p if open_p >= stop_p else stop_p
                    fill_price, slippage_amt = self.slippage_model.calculate_slippage(
                        base_price=base_p,
                        side="BUY",
                        quantity=fill_qty,
                        bar_volume=bar_vol,
                    )
            elif order.side.upper() == "SELL":
                if low_p <= stop_p:
                    # Triggered! Gap down handling:
                    base_p = open_p if open_p <= stop_p else stop_p
                    fill_price, slippage_amt = self.slippage_model.calculate_slippage(
                        base_price=base_p,
                        side="SELL",
                        quantity=fill_qty,
                        bar_volume=bar_vol,
                    )

        # -------------------------------------------------------------
        # STOP LIMIT ORDER
        # -------------------------------------------------------------
        elif o_type == "STOP_LIMIT":
            if order.stop_price is None or order.limit_price is None:
                return None
            stop_p = to_decimal(order.stop_price)
            limit_p = to_decimal(order.limit_price)

            is_triggered = order.metadata.get("stop_triggered", False)
            if not is_triggered:
                # Check trigger
                if order.side.upper() == "BUY" and high_p >= stop_p:
                    order.metadata["stop_triggered"] = True
                    is_triggered = True
                elif order.side.upper() == "SELL" and low_p <= stop_p:
                    order.metadata["stop_triggered"] = True
                    is_triggered = True

            if is_triggered:
                # Evaluate limit condition conservatively
                if order.side.upper() == "BUY" and low_p <= limit_p:
                    fill_price = min(limit_p, open_p if open_p <= limit_p else limit_p)
                elif order.side.upper() == "SELL" and high_p >= limit_p:
                    fill_price = max(limit_p, open_p if open_p >= limit_p else limit_p)

        # -------------------------------------------------------------
        # TRAILING STOP ORDER
        # -------------------------------------------------------------
        elif o_type == "TRAILING_STOP":
            if order.trailing_offset is None:
                return None
            offset = to_decimal(order.trailing_offset)

            if order.side.upper() == "SELL":
                # Long position trailing stop: tracks peak high
                current_ref = to_decimal(order.trailing_reference_price or bar.high)
                new_ref = max(current_ref, high_p)
                order.trailing_reference_price = float(new_ref)
                stop_trigger = new_ref - offset

                if low_p <= stop_trigger:
                    base_p = open_p if open_p <= stop_trigger else stop_trigger
                    fill_price, slippage_amt = self.slippage_model.calculate_slippage(
                        base_price=base_p,
                        side="SELL",
                        quantity=fill_qty,
                        bar_volume=bar_vol,
                    )
            elif order.side.upper() == "BUY":
                # Short position trailing stop: tracks trough low
                current_ref = to_decimal(order.trailing_reference_price or bar.low)
                new_ref = min(current_ref, low_p)
                order.trailing_reference_price = float(new_ref)
                stop_trigger = new_ref + offset

                if high_p >= stop_trigger:
                    base_p = open_p if open_p >= stop_trigger else stop_trigger
                    fill_price, slippage_amt = self.slippage_model.calculate_slippage(
                        base_price=base_p,
                        side="BUY",
                        quantity=fill_qty,
                        bar_volume=bar_vol,
                    )

        if fill_price is None or fill_price <= Decimal("0.0"):
            return None

        # 5. Calculate Fees
        fee_res = self.fee_model.calculate_fee(
            symbol=order.symbol,
            asset_class=order.asset_class,
            side=order.side,
            quantity=fill_qty,
            fill_price=fill_price,
        )

        # 6. Record consumed volume in bar
        self._bar_consumed_volume[bar_key] = consumed_so_far + fill_qty

        # 7. Construct SimulatedFill entity
        fill_id = f"fill_{uuid.uuid4().hex[:12]}"
        return SimulatedFill(
            simulated_fill_id=fill_id,
            simulated_order_id=order.simulated_order_id,
            intent_id=order.intent_id,
            bot_session_id=order.bot_session_id,
            symbol=order.symbol,
            side=order.side,
            fill_price=float(quantize_currency(fill_price, decimals=4)),
            fill_qty=float(fill_qty),
            fill_time=bar.event_time if isinstance(bar.event_time, datetime) else datetime.now(timezone.utc),
            fee=float(fee_res.fee_amount),
            fee_currency=fee_res.fee_currency,
            slippage=float(slippage_amt),
            source_bar_key=order.source_bar_key,
            execution_bar_key=bar.bar_key,
            assumptions=f"{self.slippage_model.get_metadata().get('model_name')}_BAR_EXEC",
            metadata={
                "order_type": order.order_type,
                "slippage_model": self.slippage_model.get_metadata(),
                "fee_model": fee_res.metadata,
                "bar_volume": float(bar_vol),
            },
            environment="SIMULATION",
        )
