"""
libs/bot/normalization.py — Market Data Normalization (GĐ30)
Normalizes raw Stocks (stock-prices) and Crypto (crypto-bars-1m) streams into MarketDataEvent.
Enforces UTC timestamps, decimal precision, symbol standardization, and provenance tagging.
"""

from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import uuid
import logging

from libs.bot.domain import MarketDataEvent

logger = logging.getLogger("market-data-normalizer")


class NormalizationError(Exception):
    """Raised when an incoming raw record violates schema constraints or missing mandatory fields."""
    def __init__(self, message: str, reason_code: str, raw_payload: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.reason_code = reason_code
        self.raw_payload = raw_payload or {}


class MarketDataNormalizer:
    """
    Normalizes heterogeneous streaming records into uniform MarketDataEvent entities.
    Handles Alpaca IEX stock bars and Alpaca Crypto WebSocket/REST 1m bars.
    """

    MANDATORY_FIELDS = {"open", "high", "low", "close"}

    @staticmethod
    def _parse_utc_datetime(val: Any) -> datetime:
        """Parses millisecond int, second int, or ISO string to UTC datetime."""
        if val is None:
            raise NormalizationError("Missing timestamp value", "ERR_MISSING_TIMESTAMP")

        if isinstance(val, (int, float)):
            # Check if millisecond (> 10 digits) or second (10 digits)
            if val > 1e11:  # Milliseconds
                return datetime.fromtimestamp(val / 1000.0, tz=timezone.utc)
            return datetime.fromtimestamp(float(val), tz=timezone.utc)

        if isinstance(val, str):
            try:
                # ISO format or millisecond string
                if val.isdigit():
                    num = int(val)
                    return MarketDataNormalizer._parse_utc_datetime(num)
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception as e:
                raise NormalizationError(f"Cannot parse timestamp string '{val}': {e}", "ERR_INVALID_TIMESTAMP")

        if isinstance(val, datetime):
            if val.tzinfo is None:
                return val.replace(tzinfo=timezone.utc)
            return val.astimezone(timezone.utc)

        raise NormalizationError(f"Unsupported timestamp type {type(val)}", "ERR_INVALID_TIMESTAMP_TYPE")

    @staticmethod
    def _to_float_precision_safe(val: Any, field_name: str) -> float:
        """Converts numerical value safely using Decimal to verify validity and avoid precision distortion."""
        if val is None:
            raise NormalizationError(f"Mandatory numeric field '{field_name}' is None", f"ERR_MISSING_FIELD_{field_name.upper()}")
        try:
            d = Decimal(str(val))
            if d.is_nan() or d.is_infinite():
                raise NormalizationError(f"Numeric field '{field_name}' is NaN or Infinity", f"ERR_INVALID_NUMERIC_{field_name.upper()}")
            return float(d)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise NormalizationError(f"Failed to parse numeric '{field_name}'='{val}': {exc}", f"ERR_PARSING_NUMERIC_{field_name.upper()}")

    @classmethod
    def normalize_symbol(cls, raw_sym: Any, asset_class: str) -> str:
        """Standardizes symbols (e.g., BTCUSD -> BTC/USD for crypto, uppercase for stocks)."""
        if not raw_sym or not isinstance(raw_sym, str):
            raise NormalizationError("Invalid or missing symbol", "ERR_INVALID_SYMBOL")

        clean = raw_sym.strip().upper()
        if asset_class == "CRYPTO":
            if "/" not in clean:
                if clean.endswith("USD"):
                    base = clean[:-3]
                    clean = f"{base}/USD"
                elif clean.endswith("USDT"):
                    base = clean[:-4]
                    clean = f"{base}/USDT"
            return clean

        return clean

    @classmethod
    def normalize_stocks_record(
        cls,
        payload: Dict[str, Any],
        provenance: str = "NATURAL_RUNTIME",
    ) -> MarketDataEvent:
        """
        Normalizes a stock bar record from 'stock-prices'.
        Expected fields: symbol, open, high, low, close, volume, trade_count, vwap, timestamp, provider.
        Stock bars polled in V1 are finalized 1m bars.
        """
        if not isinstance(payload, dict):
            raise NormalizationError("Payload must be a dictionary", "ERR_INVALID_PAYLOAD_TYPE")

        # 1. Symbol & asset class
        raw_symbol = payload.get("symbol")
        symbol = cls.normalize_symbol(raw_symbol, "STOCKS")

        # 2. Timestamp
        raw_ts = payload.get("timestamp") or payload.get("timestamp_ms") or payload.get("event_time")
        event_time = cls._parse_utc_datetime(raw_ts)

        # 3. Ingest time
        raw_ingest = payload.get("ingest_time")
        ingest_time = cls._parse_utc_datetime(raw_ingest) if raw_ingest else datetime.now(timezone.utc)

        # 4. Mandatory OHLC
        for f in cls.MANDATORY_FIELDS:
            if f not in payload or payload[f] is None:
                raise NormalizationError(f"Missing mandatory OHLC field: {f}", f"ERR_MISSING_FIELD_{f.upper()}", payload)

        open_val = cls._to_float_precision_safe(payload["open"], "open")
        high_val = cls._to_float_precision_safe(payload["high"], "high")
        low_val = cls._to_float_precision_safe(payload["low"], "low")
        close_val = cls._to_float_precision_safe(payload["close"], "close")

        # 5. Volume & auxiliary metrics
        volume = cls._to_float_precision_safe(payload.get("volume", 0.0), "volume")
        trade_count = int(cls._to_float_precision_safe(payload.get("trade_count", 0), "trade_count"))
        vwap = cls._to_float_precision_safe(payload.get("vwap", close_val), "vwap")

        # 6. Finalization & revision
        is_final = bool(payload.get("is_final", True))  # Stock 1m bars from Alpaca IEX are finalized
        revision = int(payload.get("revision", payload.get("bar_revision", 0)))
        source = str(payload.get("provider", payload.get("source", "ALPACA_STOCKS")))

        return MarketDataEvent(
            event_id=f"mde_{uuid.uuid4().hex[:12]}",
            source_event_id=str(payload.get("id", payload.get("event_id", ""))) or None,
            symbol=symbol,
            asset_class="STOCKS",
            timeframe="1m",
            open=open_val,
            high=high_val,
            low=low_val,
            close=close_val,
            volume=volume,
            trade_count=trade_count,
            vwap=vwap,
            event_time=event_time,
            ingest_time=ingest_time,
            bar_revision=revision,
            is_final=is_final,
            source=source,
            environment="SIMULATION",
            provenance=provenance,
            quality_flags=[],
        )

    @classmethod
    def normalize_crypto_record(
        cls,
        payload: Dict[str, Any],
        provenance: str = "NATURAL_RUNTIME",
    ) -> MarketDataEvent:
        """
        Normalizes a crypto bar record from 'crypto-bars-1m'.
        Expected fields: symbol, open, high, low, close, volume, trade_count, vwap,
        timestamp_ms / event_time, is_final, source.
        """
        if not isinstance(payload, dict):
            raise NormalizationError("Payload must be a dictionary", "ERR_INVALID_PAYLOAD_TYPE")

        # 1. Symbol
        raw_symbol = payload.get("symbol") or payload.get("S")
        symbol = cls.normalize_symbol(raw_symbol, "CRYPTO")

        # 2. Timestamp
        raw_ts = payload.get("timestamp_ms") or payload.get("timestamp") or payload.get("event_time") or payload.get("t")
        event_time = cls._parse_utc_datetime(raw_ts)

        # 3. Ingest time
        raw_ingest = payload.get("ingest_time")
        ingest_time = cls._parse_utc_datetime(raw_ingest) if raw_ingest else datetime.now(timezone.utc)

        # 4. Mandatory OHLC
        o_val = payload.get("open") if "open" in payload else payload.get("o")
        h_val = payload.get("high") if "high" in payload else payload.get("h")
        l_val = payload.get("low") if "low" in payload else payload.get("l")
        c_val = payload.get("close") if "close" in payload else payload.get("c")

        if any(v is None for v in [o_val, h_val, l_val, c_val]):
            missing = [k for k, v in [("open", o_val), ("high", h_val), ("low", l_val), ("close", c_val)] if v is None]
            raise NormalizationError(f"Missing mandatory OHLC fields: {missing}", "ERR_MISSING_OHLC", payload)

        open_val = cls._to_float_precision_safe(o_val, "open")
        high_val = cls._to_float_precision_safe(h_val, "high")
        low_val = cls._to_float_precision_safe(l_val, "low")
        close_val = cls._to_float_precision_safe(c_val, "close")

        # 5. Volume & metrics
        vol_raw = payload.get("volume") if "volume" in payload else payload.get("v", 0.0)
        volume = cls._to_float_precision_safe(vol_raw, "volume")
        tc_raw = payload.get("trade_count") if "trade_count" in payload else payload.get("n", 0)
        trade_count = int(cls._to_float_precision_safe(tc_raw, "trade_count"))
        vw_raw = payload.get("vwap") if "vwap" in payload else payload.get("vw", close_val)
        vwap = cls._to_float_precision_safe(vw_raw, "vwap")

        # 6. Finalization & revision
        is_final = bool(payload.get("is_final", True))
        revision = int(payload.get("revision", payload.get("bar_revision", 0)))
        source = str(payload.get("source", payload.get("provider", "ALPACA_CRYPTO")))

        return MarketDataEvent(
            event_id=f"mde_{uuid.uuid4().hex[:12]}",
            source_event_id=str(payload.get("id", payload.get("event_id", ""))) or None,
            symbol=symbol,
            asset_class="CRYPTO",
            timeframe="1m",
            open=open_val,
            high=high_val,
            low=low_val,
            close=close_val,
            volume=volume,
            trade_count=trade_count,
            vwap=vwap,
            event_time=event_time,
            ingest_time=ingest_time,
            bar_revision=revision,
            is_final=is_final,
            source=source,
            environment="SIMULATION",
            provenance=provenance,
            quality_flags=[],
        )

    @classmethod
    def normalize_raw(
        cls,
        topic: str,
        payload: Dict[str, Any],
        provenance: str = "NATURAL_RUNTIME",
    ) -> MarketDataEvent:
        """Inspects topic or payload metadata and dispatches to appropriate normalizer."""
        if "crypto" in topic.lower() or payload.get("asset_type") == "crypto" or "/" in str(payload.get("symbol", "")):
            return cls.normalize_crypto_record(payload, provenance=provenance)
        return cls.normalize_stocks_record(payload, provenance=provenance)
