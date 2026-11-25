"""
libs/bot/backtesting/trade_ledger.py — Backtest Chart Indicator Series & Closed-Trade Ledger (GĐ41)
Computes strategy-exact indicator series (SMA Fast/Slow, RSI 14) using libs.bot.indicators
and derives deterministic closed-trade entry/exit associations from SimulatedFills matching
the SimulationPortfolioManager / PositionBook weighted-average accounting contract.
"""

from dataclasses import replace
from decimal import Decimal
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import uuid

from libs.bot.domain import MarketDataEvent
from libs.bot.backtesting.dataset import HistoricalDatasetManager
from libs.bot.indicators.sma import SMAIndicator
from libs.bot.indicators.rsi import RSIIndicator

_NY_TZ = ZoneInfo("America/New_York")


def _to_utc_epoch(dt: Any) -> int:
    """Converts a datetime or ISO string to UTC integer Unix timestamp seconds."""
    if isinstance(dt, datetime):
        d = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        return int(d.astimezone(timezone.utc).timestamp())
    if isinstance(dt, (int, float)):
        return int(dt)
    d = datetime.fromisoformat(str(dt))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(d.astimezone(timezone.utc).timestamp())


def serialize_candles(
    bars: List[MarketDataEvent],
    warmup_count: int = 0,
    asset_classes: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Serializes MarketDataEvent bars to UTC OHLCV candle records with session and warmup flags."""
    serialized: List[Dict[str, Any]] = []
    for idx, b in enumerate(bars):
        dt = b.event_time if b.event_time.tzinfo is not None else b.event_time.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        inferred_ac = "CRYPTO" if "/" in b.symbol else "STOCKS"
        ac = (asset_classes or {}).get(b.symbol) or getattr(b, "asset_class", None) or inferred_ac
        session = HistoricalDatasetManager.classify_market_session(dt_utc, ac)
        serialized.append({
            "time": int(dt_utc.timestamp()),
            "timestamp": dt_utc.isoformat(),
            "ny_time": dt_utc.astimezone(_NY_TZ).strftime("%Y-%m-%d %H:%M"),
            "session": session,
            "symbol": b.symbol,
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": float(b.volume),
            "is_warmup": idx < warmup_count,
            "bar_key": b.bar_key,
        })
    return serialized


def compute_strategy_indicators(
    bars: List[MarketDataEvent],
    strategy_id: str,
    execution_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Computes indicator series (MA Fast, MA Slow, RSI) strictly bar-by-bar using the
    Strategy Engine indicator implementations without look-ahead bias.
    Incomplete warmup bars emit value=None.
    """
    params = (execution_config or {}).get("strategy_params", {})
    fast_period = int(params.get("fast_period", params.get("short_window", 20)))
    slow_period = int(params.get("slow_period", params.get("long_window", 50)))
    rsi_period = int(params.get("period", 14))
    rsi_method = str(params.get("method", "SIMPLE_ROLLING")).upper()
    if rsi_method not in ("SIMPLE_ROLLING", "WILDER"):
        rsi_method = "SIMPLE_ROLLING"
    rsi_oversold = float(params.get("oversold", 30.0))
    rsi_overbought = float(params.get("overbought", 70.0))

    if fast_period >= slow_period:
        slow_period = fast_period + 1

    series_by_symbol: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    indicators_by_symbol: Dict[str, Dict[str, Any]] = {}
    readiness_by_symbol: Dict[str, Dict[str, Any]] = {}

    for bar in bars:
        sym = bar.symbol
        if sym not in indicators_by_symbol:
            indicators_by_symbol[sym] = {
                "fast": SMAIndicator(period=fast_period),
                "slow": SMAIndicator(period=slow_period),
                "rsi": RSIIndicator(period=rsi_period, method=rsi_method),
            }
            series_by_symbol[sym] = {
                "ma_fast": [],
                "ma_slow": [],
                "rsi": [],
            }
            readiness_by_symbol[sym] = {
                "total_bars": 0,
                "ma_fast_ready_bar": None,
                "ma_slow_ready_bar": None,
                "rsi_ready_bar": None,
                "ma_fast_ready_time": None,
                "ma_slow_ready_time": None,
                "rsi_ready_time": None,
            }

        ind = indicators_by_symbol[sym]
        # Ensure float close for indicator arithmetic compatibility with Decimal-backed fixtures
        eval_bar = bar if isinstance(bar.close, float) else replace(bar, close=float(bar.close))
        fast_res = ind["fast"].update(eval_bar)
        slow_res = ind["slow"].update(eval_bar)
        rsi_res = ind["rsi"].update(eval_bar)

        dt = bar.event_time if bar.event_time.tzinfo is not None else bar.event_time.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        epoch = int(dt_utc.timestamp())
        iso = dt_utc.isoformat()

        r_meta = readiness_by_symbol[sym]
        bar_num = r_meta["total_bars"] + 1
        r_meta["total_bars"] = bar_num
        if fast_res.warmup_complete and r_meta["ma_fast_ready_bar"] is None:
            r_meta["ma_fast_ready_bar"] = bar_num
            r_meta["ma_fast_ready_time"] = iso
        if slow_res.warmup_complete and r_meta["ma_slow_ready_bar"] is None:
            r_meta["ma_slow_ready_bar"] = bar_num
            r_meta["ma_slow_ready_time"] = iso
        if rsi_res.warmup_complete and r_meta["rsi_ready_bar"] is None:
            r_meta["rsi_ready_bar"] = bar_num
            r_meta["rsi_ready_time"] = iso

        series_by_symbol[sym]["ma_fast"].append({
            "time": epoch,
            "timestamp": iso,
            "value": float(fast_res.value) if fast_res.warmup_complete and fast_res.value is not None else None,
            "warmup_complete": fast_res.warmup_complete,
        })
        series_by_symbol[sym]["ma_slow"].append({
            "time": epoch,
            "timestamp": iso,
            "value": float(slow_res.value) if slow_res.warmup_complete and slow_res.value is not None else None,
            "warmup_complete": slow_res.warmup_complete,
        })
        series_by_symbol[sym]["rsi"].append({
            "time": epoch,
            "timestamp": iso,
            "value": float(rsi_res.value) if rsi_res.warmup_complete and rsi_res.value is not None else None,
            "warmup_complete": rsi_res.warmup_complete,
        })

    return {
        "strategy_id": strategy_id,
        "params": {
            "fast_period": fast_period,
            "slow_period": slow_period,
            "rsi_period": rsi_period,
            "rsi_method": rsi_method,
            "rsi_oversold": rsi_oversold,
            "rsi_overbought": rsi_overbought,
        },
        "readiness_by_symbol": readiness_by_symbol,
        "series_by_symbol": series_by_symbol,
    }


def build_closed_trades_and_associations(
    fills: List[Dict[str, Any]],
    signals_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Matches entry and exit fills chronologically per symbol using the weighted-average
    cost basis accounting model (matching PositionBook.record_fill) and emits closed trade
    associations with gross/net P&L, fees, slippage, holding duration, and signal reasons.
    """
    if not fills:
        return []

    sig_map = signals_by_id or {}
    ordered = sorted(
        fills,
        key=lambda f: _to_utc_epoch(f.get("fill_time", 0)),
    )

    # State per symbol: {"qty": Decimal (+long, -short), "avg_price": Decimal, "open_entries": List[Dict]}
    book: Dict[str, Dict[str, Any]] = {}
    closed_trades: List[Dict[str, Any]] = []
    trade_seq = 0

    for fill in ordered:
        sym = fill["symbol"]
        side = str(fill["side"]).upper()
        qty = Decimal(str(fill["fill_qty"]))
        price = Decimal(str(fill["fill_price"]))
        fee = Decimal(str(fill.get("fee", 0.0)))
        slippage = Decimal(str(fill.get("slippage", 0.0)))

        if qty <= Decimal("0") or price <= Decimal("0"):
            continue

        if sym not in book:
            book[sym] = {"qty": Decimal("0"), "avg_price": Decimal("0"), "open_entries": []}

        state = book[sym]
        curr_qty = state["qty"]
        curr_avg = state["avg_price"]

        def _entry_meta() -> Dict[str, Any]:
            s_id = fill.get("signal_id")
            sig_info = sig_map.get(s_id, {}) if s_id else {}
            return {
                "fill_id": fill["simulated_fill_id"],
                "order_id": fill["simulated_order_id"],
                "time": fill["fill_time"],
                "epoch": _to_utc_epoch(fill["fill_time"]),
                "price": float(price),
                "remaining_qty": qty,
                "orig_qty": qty,
                "remaining_fee": fee,
                "remaining_slippage": slippage,
                "reason": fill.get("strategy_reason") or sig_info.get("reason") or "",
            }

        is_opening_long = side == "BUY" and curr_qty >= Decimal("0")
        is_opening_short = side == "SELL" and curr_qty <= Decimal("0")

        if is_opening_long:
            new_qty = curr_qty + qty
            state["avg_price"] = ((curr_qty * curr_avg) + (qty * price)) / new_qty
            state["qty"] = new_qty
            state["open_entries"].append(_entry_meta())
        elif is_opening_short:
            abs_curr = abs(curr_qty)
            new_abs = abs_curr + qty
            state["avg_price"] = ((abs_curr * curr_avg) + (qty * price)) / new_abs
            state["qty"] = -new_abs
            state["open_entries"].append(_entry_meta())
        else:
            # Closing/trimming existing Long (side == SELL, curr_qty > 0) or Short (side == BUY, curr_qty < 0)
            is_long_close = curr_qty > Decimal("0") and side == "SELL"
            avail = abs(curr_qty)
            close_qty = min(avail, qty)

            gross_pnl = (price - curr_avg) * close_qty if is_long_close else (curr_avg - price) * close_qty

            # Consume open entry lots proportionally / FIFO for entry attribution
            to_consume = close_qty
            entry_fill_ids: List[str] = []
            entry_order_ids: List[str] = []
            entry_reasons: List[str] = []
            alloc_entry_fee = Decimal("0")
            alloc_entry_slip = Decimal("0")
            first_entry_time = None
            first_entry_epoch = None

            while to_consume > Decimal("1e-9") and state["open_entries"]:
                lot = state["open_entries"][0]
                if first_entry_time is None:
                    first_entry_time = lot["time"]
                    first_entry_epoch = lot["epoch"]
                take = min(lot["remaining_qty"], to_consume)
                ratio = take / lot["remaining_qty"] if lot["remaining_qty"] > Decimal("0") else Decimal("0")
                alloc_entry_fee += lot["remaining_fee"] * ratio
                alloc_entry_slip += lot["remaining_slippage"] * ratio
                lot["remaining_fee"] -= lot["remaining_fee"] * ratio
                lot["remaining_slippage"] -= lot["remaining_slippage"] * ratio
                lot["remaining_qty"] -= take
                to_consume -= take

                if lot["fill_id"] not in entry_fill_ids:
                    entry_fill_ids.append(lot["fill_id"])
                if lot["order_id"] not in entry_order_ids:
                    entry_order_ids.append(lot["order_id"])
                if lot["reason"] and lot["reason"] not in entry_reasons:
                    entry_reasons.append(lot["reason"])

                if lot["remaining_qty"] <= Decimal("1e-9"):
                    state["open_entries"].pop(0)

            exit_ratio = close_qty / qty if qty > Decimal("0") else Decimal("1")
            alloc_exit_fee = fee * exit_ratio
            alloc_exit_slip = slippage * exit_ratio
            total_fees = alloc_entry_fee + alloc_exit_fee
            total_slip = alloc_entry_slip + alloc_exit_slip
            net_pnl = gross_pnl - total_fees
            notional_entry = curr_avg * close_qty
            return_pct = float((net_pnl / notional_entry) * Decimal("100")) if notional_entry > Decimal("0") else 0.0

            exit_epoch = _to_utc_epoch(fill["fill_time"])
            duration_sec = max(0, exit_epoch - (first_entry_epoch or exit_epoch))
            exit_reason = fill.get("strategy_reason") or sig_map.get(fill.get("signal_id", ""), {}).get("reason", "")

            trade_seq += 1
            closed_trades.append({
                "trade_id": f"trd_{trade_seq:04d}_{uuid.uuid4().hex[:6]}",
                "symbol": sym,
                "direction": "LONG" if is_long_close else "SHORT",
                "entry_fill_ids": entry_fill_ids,
                "exit_fill_id": fill["simulated_fill_id"],
                "entry_order_ids": entry_order_ids,
                "exit_order_id": fill["simulated_order_id"],
                "entry_time": first_entry_time or fill["fill_time"],
                "exit_time": fill["fill_time"],
                "entry_epoch": first_entry_epoch or exit_epoch,
                "exit_epoch": exit_epoch,
                "entry_price": round(float(curr_avg), 4),
                "exit_price": round(float(price), 4),
                "qty": float(close_qty),
                "gross_pnl": round(float(gross_pnl), 4),
                "fees": round(float(total_fees), 4),
                "slippage": round(float(total_slip), 4),
                "net_pnl": round(float(net_pnl), 4),
                "return_pct": round(return_pct, 4),
                "is_win": float(net_pnl) > 0.0,
                "duration_seconds": duration_sec,
                "entry_reason": "; ".join(entry_reasons),
                "exit_reason": exit_reason,
                "strategy_id": fill.get("strategy_id", ""),
            })

            # Update remaining position
            leftover = qty - close_qty
            if is_long_close:
                new_qty = curr_qty - qty
            else:
                new_qty = curr_qty + qty

            if abs(new_qty) < Decimal("1e-9"):
                state["qty"] = Decimal("0")
                state["avg_price"] = Decimal("0")
                state["open_entries"].clear()
            elif leftover > Decimal("1e-9"):
                # Reversed position with leftover quantity
                state["qty"] = new_qty
                state["avg_price"] = price
                rev_fee = fee * (leftover / qty)
                rev_slip = slippage * (leftover / qty)
                rev_meta = _entry_meta()
                rev_meta["remaining_qty"] = leftover
                rev_meta["orig_qty"] = leftover
                rev_meta["remaining_fee"] = rev_fee
                rev_meta["remaining_slippage"] = rev_slip
                state["open_entries"] = [rev_meta]
            else:
                state["qty"] = new_qty

    return closed_trades
