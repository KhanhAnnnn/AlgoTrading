"""
libs/bot/quality.py — Data Quality, Validation & Freshness Engine (GĐ30)
Validates schemas, OHLC consistency, volume sanity, timestamp bounds,
duplicates, late/out-of-order arrivals, missing intervals, and market calendars.
"""

from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime, timezone, timedelta
import zoneinfo
import logging

from libs.bot.domain import MarketDataEvent

logger = logging.getLogger("data-quality-engine")


class DataQualityEngine:
    """
    Performs comprehensive data quality verification on streaming and historical 1m bars.
    Rejects invalid records with explicit reason codes, preventing silent data corruption.
    """

    # US Equities Market Hours in Eastern Time
    US_EASTERN = zoneinfo.ZoneInfo("America/New_York")

    def __init__(self, max_future_skew_seconds: float = 300.0, stale_threshold_seconds: float = 300.0):
        self.max_future_skew = timedelta(seconds=max_future_skew_seconds)
        self.stale_threshold = timedelta(seconds=stale_threshold_seconds)
        # Tracking seen event IDs and hashes for duplicate detection
        self._seen_event_ids: Set[str] = set()
        self._seen_signatures: Set[str] = set()
        # Per-symbol latest event times for late/out-of-order detection
        self._latest_event_times: Dict[str, datetime] = {}
        # Per-symbol last bar for missing interval detection
        self._last_bars: Dict[str, MarketDataEvent] = {}
        # Rejection counter and logs
        self.rejected_records: List[Dict[str, Any]] = []
        self.total_checked = 0
        self.total_passed = 0
        self.total_rejected = 0

    def _generate_signature(self, bar: MarketDataEvent) -> str:
        """Computes content signature for duplicate detection."""
        return f"{bar.symbol}:{bar.timeframe}:{bar.event_time.isoformat()}:{bar.open}:{bar.high}:{bar.low}:{bar.close}:{bar.volume}:{bar.bar_revision}"

    @classmethod
    def is_stocks_market_open(cls, dt_utc: datetime) -> Tuple[bool, str]:
        """
        Evaluates whether a given UTC timestamp falls within US Regular Market Hours:
        Monday-Friday 09:30 - 16:00 US/Eastern.
        Returns (is_open, description).
        """
        dt_et = dt_utc.astimezone(cls.US_EASTERN)
        weekday = dt_et.weekday()  # 0 is Monday, 6 is Sunday

        if weekday >= 5:
            return False, f"WEEKEND (Day {weekday})"

        market_open = dt_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = dt_et.replace(hour=16, minute=0, second=0, microsecond=0)

        if market_open <= dt_et <= market_close:
            return True, "REGULAR_MARKET_HOURS"
        if dt_et < market_open:
            return False, "PRE_MARKET"
        return False, "AFTER_HOURS"

    def validate_bar(self, bar: MarketDataEvent) -> Tuple[bool, List[str], Optional[str]]:
        """
        Validates a single MarketDataEvent.
        Returns:
            Tuple of (is_valid: bool, quality_flags: List[str], rejection_reason: Optional[str])
        """
        self.total_checked += 1
        flags: List[str] = []
        rejection_code: Optional[str] = None
        now_utc = datetime.now(timezone.utc)

        # 1. Environment & Timeframe
        if bar.environment != "SIMULATION":
            rejection_code = "ERR_INVALID_ENVIRONMENT"
            flags.append("INVALID_ENVIRONMENT")

        if bar.timeframe != "1m":
            rejection_code = "ERR_INVALID_TIMEFRAME"
            flags.append("INVALID_TIMEFRAME")

        # 2. Timestamp sanity
        if not isinstance(bar.event_time, datetime) or bar.event_time.tzinfo is None:
            rejection_code = "ERR_TIMEZONE_UNAWARE"
            flags.append("TIMEZONE_UNAWARE")
        elif bar.event_time > now_utc + self.max_future_skew:
            rejection_code = "ERR_FUTURE_TIMESTAMP_SKEW"
            flags.append("FUTURE_TIMESTAMP")
        elif bar.event_time.year < 2000:
            rejection_code = "ERR_EPOCH_ZERO_TIMESTAMP"
            flags.append("EPOCH_ZERO")

        # 3. OHLC Consistency
        if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
            rejection_code = "ERR_NON_POSITIVE_PRICE"
            flags.append("NON_POSITIVE_PRICE")

        if bar.high < bar.open or bar.high < bar.close or bar.high < bar.low:
            rejection_code = "ERR_OHLC_HIGH_VIOLATION"
            flags.append("HIGH_LESS_THAN_OPEN_OR_CLOSE")

        if bar.low > bar.open or bar.low > bar.close or bar.low > bar.high:
            rejection_code = "ERR_OHLC_LOW_VIOLATION"
            flags.append("LOW_GREATER_THAN_OPEN_OR_CLOSE")

        # 4. Volume sanity
        if bar.volume < 0:
            rejection_code = "ERR_NEGATIVE_VOLUME"
            flags.append("NEGATIVE_VOLUME")

        # 5. Duplicate Detection
        sig = self._generate_signature(bar)
        if bar.event_id in self._seen_event_ids or sig in self._seen_signatures:
            flags.append("DUPLICATE_BAR")
            # If exact identical signature seen with same revision, reject as duplicate
            if sig in self._seen_signatures and bar.bar_revision == 0:
                rejection_code = "ERR_DUPLICATE_EVENT"

        # 6. Out-of-order & Late Detection
        symbol = bar.symbol
        if symbol in self._latest_event_times:
            last_event_time = self._latest_event_times[symbol]
            if bar.event_time < last_event_time:
                time_lag = last_event_time - bar.event_time
                if time_lag > timedelta(minutes=5):
                    flags.append("LATE_EVENT")
                else:
                    flags.append("OUT_OF_ORDER_EVENT")

        # 7. Missing Interval (Gap) Detection
        if symbol in self._last_bars:
            prev_bar = self._last_bars[symbol]
            delta = bar.event_time - prev_bar.event_time
            if delta > timedelta(minutes=1):
                # For stocks, check if market was closed in between
                if bar.asset_class == "STOCKS":
                    was_open, _ = self.is_stocks_market_open(prev_bar.event_time)
                    if was_open and delta > timedelta(minutes=2):
                        flags.append(f"MISSING_INTERVAL_GAP_{int(delta.total_seconds() / 60)}M")
                else:
                    flags.append(f"MISSING_INTERVAL_GAP_{int(delta.total_seconds() / 60)}M")

        # 8. Calendar checks
        if bar.asset_class == "STOCKS":
            is_open, desc = self.is_stocks_market_open(bar.event_time)
            if not is_open:
                flags.append(f"STOCKS_{desc}")

        # Final decision
        is_valid = rejection_code is None
        bar.quality_flags = list(set(bar.quality_flags + flags))

        if is_valid:
            self.total_passed += 1
            self._seen_event_ids.add(bar.event_id)
            self._seen_signatures.add(sig)
            if symbol not in self._latest_event_times or bar.event_time > self._latest_event_times[symbol]:
                self._latest_event_times[symbol] = bar.event_time
            self._last_bars[symbol] = bar
        else:
            self.total_rejected += 1
            self.rejected_records.append({
                "event_id": bar.event_id,
                "symbol": bar.symbol,
                "event_time": bar.event_time.isoformat(),
                "reason_code": rejection_code,
                "flags": flags,
                "timestamp": now_utc.isoformat(),
            })

        return is_valid, bar.quality_flags, rejection_code

    def get_quality_summary(self) -> Dict[str, Any]:
        """Returns aggregate quality statistics."""
        return {
            "total_checked": self.total_checked,
            "total_passed": self.total_passed,
            "total_rejected": self.total_rejected,
            "pass_rate_pct": (self.total_passed / self.total_checked * 100.0) if self.total_checked > 0 else 100.0,
            "rejected_count": len(self.rejected_records),
            "sample_rejections": self.rejected_records[-5:] if self.rejected_records else [],
        }
