"""
libs/bot/backtesting/dataset.py — Historical Dataset Manager & Manifests (GĐ36 & GĐ41)
Provides normalized, versioned, checksum-validated historical 1m datasets for Stocks and Crypto.
Supports Alpaca real historical market data provenance, local cache persistence, gap detection,
and immutable dataset snapshots for deterministic backtesting.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timezone, time, date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
import hashlib
import json
import logging
import os
import uuid

from libs.bot.domain import MarketDataEvent
from libs.bot.normalization import MarketDataNormalizer

logger = logging.getLogger("backtest-dataset")

_NY_TZ = ZoneInfo("America/New_York")

# US Equity Market Holidays (NYSE full closures, 2024-2027)
_US_MARKET_HOLIDAYS: Set[date] = {
    # 2024
    date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19), date(2024, 3, 29),
    date(2024, 5, 27), date(2024, 6, 19), date(2024, 7, 4), date(2024, 9, 2),
    date(2024, 11, 28), date(2024, 12, 25),
    # 2025
    date(2025, 1, 1), date(2025, 1, 9), date(2025, 1, 20), date(2025, 2, 17),
    date(2025, 4, 18), date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4),
    date(2025, 9, 1), date(2025, 11, 27), date(2025, 12, 25),
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    # 2027
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
    date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 11, 25), date(2027, 12, 24),
}

# NYSE 13:00 ET early close dates (2024-2027)
_US_EARLY_CLOSE_DATES: Set[date] = {
    date(2024, 7, 3), date(2024, 11, 29), date(2024, 12, 24),
    date(2025, 7, 3), date(2025, 11, 28), date(2025, 12, 24),
    date(2026, 11, 27), date(2026, 12, 24),
    date(2027, 11, 26),
}


@dataclass
class DatasetManifest:
    """Immutable metadata and checksum for a historical backtesting dataset (GĐ41)."""
    dataset_id: str
    version: str
    symbol_counts: Dict[str, int]
    total_bars: int
    start_time: str
    end_time: str
    timeframe: str
    checksum_sha256: str
    is_synthetic: bool
    created_at: str
    environment: str = "SIMULATION"
    provider: str = "ALPACA"
    source_type: str = "REAL_HISTORICAL_MARKET_DATA"  # REAL_HISTORICAL_MARKET_DATA, SYNTHETIC_FIXTURE
    feed: str = "IEX"
    asset_class: str = "STOCKS"
    requested_start: Optional[str] = None
    requested_end: Optional[str] = None
    actual_first_bar: Optional[str] = None
    actual_last_bar: Optional[str] = None
    adjustment_policy: str = "RAW"
    duplicate_count: int = 0
    gap_count: int = 0
    completeness_status: str = "COMPLETE"  # COMPLETE, PARTIAL, EMPTY
    session_calendar_version: str = "US_EQUITIES_2026_V1"
    source_api_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def symbols(self) -> List[str]:
        return list(self.symbol_counts.keys())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DatasetManifest":
        known_keys = {
            "dataset_id", "version", "symbol_counts", "total_bars", "start_time", "end_time",
            "timeframe", "checksum_sha256", "is_synthetic", "created_at", "environment",
            "provider", "source_type", "feed", "asset_class", "requested_start", "requested_end",
            "actual_first_bar", "actual_last_bar", "adjustment_policy", "duplicate_count",
            "gap_count", "completeness_status", "session_calendar_version", "source_api_metadata",
        }
        filtered = {k: v for k, v in d.items() if k in known_keys}
        return cls(**filtered)


class InvalidBarDataError(ValueError):
    """Raised when an OHLCV bar violates mathematical or schema invariants."""
    pass


def validate_ohlcv(bar: MarketDataEvent) -> bool:
    """Module-level validator returning boolean."""
    try:
        HistoricalDatasetManager.validate_ohlcv(bar)
        return True
    except (InvalidBarDataError, ValueError):
        return False


def is_regular_trading_hours(dt: datetime, asset_class: str = "STOCKS") -> bool:
    """Module-level market hours check."""
    return HistoricalDatasetManager.is_regular_trading_hours(dt, asset_class)


class HistoricalDatasetManager:
    """
    Loads, sanitizes, validates, caches, and hashes historical datasets for deterministic backtesting.
    Enforces market hours for equities (09:30-16:00 US Eastern) and 24/7 for crypto.
    """

    def __init__(self, base_dir: str = "data/paper_bot/datasets"):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        self._datasets: Dict[str, List[MarketDataEvent]] = {}
        self._manifests: Dict[str, DatasetManifest] = {}

    @staticmethod
    def validate_ohlcv(bar: MarketDataEvent) -> None:
        """
        Validates mathematical OHLCV integrity:
        high >= low, high >= open, high >= close, low <= open, low <= close, volume >= 0.
        """
        o = float(bar.open)
        h = float(bar.high)
        l = float(bar.low)
        c = float(bar.close)
        v = float(bar.volume)

        if o <= 0 or h <= 0 or l <= 0 or c <= 0:
            raise InvalidBarDataError(f"Bar prices must be positive: O={o}, H={h}, L={l}, C={c}")
        if h < l:
            raise InvalidBarDataError(f"High ({h}) cannot be less than Low ({l})")
        if h < o or h < c:
            raise InvalidBarDataError(f"High ({h}) must be >= Open ({o}) and Close ({c})")
        if l > o or l > c:
            raise InvalidBarDataError(f"Low ({l}) must be <= Open ({o}) and Close ({c})")
        if v < 0:
            raise InvalidBarDataError(f"Volume ({v}) cannot be negative")

    @staticmethod
    def classify_market_session(dt: datetime, asset_class: str = "STOCKS") -> str:
        """
        Classifies a bar timestamp into market session using America/New_York EST/EDT:
        - CRYPTO -> CRYPTO_24_7
        - STOCKS -> RTH (09:30 <= t < close_et on Mon-Fri non-holidays),
                    PRE_MARKET (< 09:30 ET), AFTER_HOURS (>= close_et), CLOSED (weekend/holiday)
        """
        if asset_class.upper() == "CRYPTO":
            return "CRYPTO_24_7"

        dt_utc = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        ny_dt = dt_utc.astimezone(_NY_TZ)
        ny_date = ny_dt.date()

        if ny_dt.weekday() >= 5 or ny_date in _US_MARKET_HOLIDAYS:
            return "CLOSED"

        close_et = time(13, 0) if ny_date in _US_EARLY_CLOSE_DATES else time(16, 0)
        ny_t = ny_dt.time()
        if time(9, 30) <= ny_t < close_et:
            return "RTH"
        if ny_t < time(9, 30):
            return "PRE_MARKET"
        return "AFTER_HOURS"

    @staticmethod
    def is_regular_trading_hours(dt: datetime, asset_class: str = "STOCKS") -> bool:
        """
        Checks if timestamp falls within regular trading hours:
        Stocks: Mon-Fri 09:30 to <16:00 America/New_York (EST/EDT auto-adjusted, excluding holidays; 13:00 early close)
        Crypto: Continuous 24/7 (always True)
        """
        if asset_class.upper() == "CRYPTO":
            return True
        return HistoricalDatasetManager.classify_market_session(dt, asset_class) == "RTH"

    def create_dataset_from_bars(
        self,
        dataset_id: str,
        bars: List[MarketDataEvent],
        version: str = "1.0.0",
        is_synthetic: bool = False,
        enforce_session_hours: bool = False,
        asset_classes: Optional[Dict[str, str]] = None,
        provider: Optional[str] = None,
        source_type: Optional[str] = None,
        feed: str = "IEX",
        asset_class: Optional[str] = None,
        requested_start: Optional[str] = None,
        requested_end: Optional[str] = None,
        adjustment_policy: str = "RAW",
        session_calendar_version: str = "US_EQUITIES_2026_V1",
        source_api_metadata: Optional[Dict[str, Any]] = None,
        persist_to_disk: bool = True,
    ) -> Tuple[List[MarketDataEvent], DatasetManifest]:
        """
        Validates, deduplicates, sorts, hashes, caches, and packages raw bars into an immutable dataset.
        """
        if not bars:
            raise ValueError("Cannot create empty dataset")

        classes = asset_classes or {}
        sanitized: List[MarketDataEvent] = []
        seen_keys: Set[Tuple[str, datetime]] = set()
        duplicates_count = 0

        for b in bars:
            # 1. Mathematical OHLCV validation
            self.validate_ohlcv(b)

            # 2. Session hours filtering if requested
            asset_type = classes.get(b.symbol, "CRYPTO" if "/" in b.symbol or "-" in b.symbol else "STOCKS")
            if enforce_session_hours and not self.is_regular_trading_hours(b.event_time, asset_type):
                continue

            # 3. Deduplication: deterministic tie-breaker (keep latest revision or first seen)
            key = (b.symbol, b.event_time)
            if key in seen_keys:
                duplicates_count += 1
                idx = next(i for i, existing in enumerate(sanitized) if (existing.symbol, existing.event_time) == key)
                if b.bar_revision > sanitized[idx].bar_revision:
                    sanitized[idx] = b
                continue
            seen_keys.add(key)
            sanitized.append(b)

        if not sanitized:
            raise ValueError("No bars remained after applying validation and session filters")

        # 4. Strict deterministic chronological ordering: (event_time, symbol, revision)
        sanitized.sort(key=lambda x: (x.event_time, x.symbol, x.bar_revision))

        # 5. Compute SHA-256 Checksum over canonical representation
        hasher = hashlib.sha256()
        symbol_counts: Dict[str, int] = {}
        for b in sanitized:
            symbol_counts[b.symbol] = symbol_counts.get(b.symbol, 0) + 1
            line = f"{b.symbol}:{b.event_time.isoformat()}:{b.open}:{b.high}:{b.low}:{b.close}:{b.volume}:{b.bar_revision}"
            hasher.update(line.encode("utf-8"))

        primary_sym = sanitized[0].symbol
        primary_ac = asset_class or classes.get(primary_sym, "CRYPTO" if "/" in primary_sym or "-" in primary_sym else "STOCKS")
        prov = provider or ("SYNTHETIC_GENERATOR" if is_synthetic else "ALPACA")
        src_t = source_type or ("SYNTHETIC_FIXTURE" if is_synthetic else "REAL_HISTORICAL_MARKET_DATA")
        gaps = self.detect_gaps(sanitized)

        manifest = DatasetManifest(
            dataset_id=dataset_id,
            version=version,
            symbol_counts=symbol_counts,
            total_bars=len(sanitized),
            start_time=sanitized[0].event_time.isoformat(),
            end_time=sanitized[-1].event_time.isoformat(),
            timeframe=sanitized[0].timeframe,
            checksum_sha256=hasher.hexdigest(),
            is_synthetic=is_synthetic,
            created_at=datetime.now(timezone.utc).isoformat(),
            environment="SIMULATION",
            provider=prov,
            source_type=src_t,
            feed=feed.upper(),
            asset_class=primary_ac,
            requested_start=requested_start or sanitized[0].event_time.isoformat(),
            requested_end=requested_end or sanitized[-1].event_time.isoformat(),
            actual_first_bar=sanitized[0].event_time.isoformat(),
            actual_last_bar=sanitized[-1].event_time.isoformat(),
            adjustment_policy=adjustment_policy,
            duplicate_count=duplicates_count,
            gap_count=len(gaps),
            completeness_status="COMPLETE",
            session_calendar_version=session_calendar_version,
            source_api_metadata=source_api_metadata or {},
        )

        self._datasets[dataset_id] = sanitized
        self._manifests[dataset_id] = manifest

        # 6. Disk persistence if enabled
        if persist_to_disk:
            self._save_to_disk(dataset_id, sanitized, manifest)

        logger.info(
            f"Created dataset '{dataset_id}' (v{version}) with {len(sanitized)} bars, "
            f"checksum={manifest.checksum_sha256[:8]} [Provider: {manifest.provider}, Source: {manifest.source_type}]"
        )
        return sanitized, manifest

    def _save_to_disk(self, dataset_id: str, bars: List[MarketDataEvent], manifest: DatasetManifest) -> None:
        """Persists dataset manifest and bars to JSON / JSONL on disk."""
        try:
            target_dir = os.path.join(self.base_dir, dataset_id)
            os.makedirs(target_dir, exist_ok=True)

            manifest_path = os.path.join(target_dir, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest.to_dict(), f, indent=2)

            bars_path = os.path.join(target_dir, "bars.jsonl")
            with open(bars_path, "w", encoding="utf-8") as f:
                for b in bars:
                    record = {
                        "event_id": b.event_id,
                        "symbol": b.symbol,
                        "asset_class": b.asset_class,
                        "timeframe": b.timeframe,
                        "event_time": b.event_time.isoformat(),
                        "open": float(b.open),
                        "high": float(b.high),
                        "low": float(b.low),
                        "close": float(b.close),
                        "volume": float(b.volume),
                        "trade_count": getattr(b, "trade_count", 0),
                        "vwap": float(getattr(b, "vwap", 0.0)),
                        "bar_revision": b.bar_revision,
                        "is_final": b.is_final,
                        "provenance": b.provenance,
                        "environment": b.environment,
                    }
                    f.write(json.dumps(record) + "\n")
            logger.info(f"Persisted dataset '{dataset_id}' to {target_dir}")
        except Exception as e:
            logger.warning(f"Failed to persist dataset '{dataset_id}' to disk: {e}")

    def load_dataset(self, dataset_id: str) -> Optional[List[MarketDataEvent]]:
        """Loads dataset by ID from memory cache or persisted disk storage."""
        if dataset_id in self._datasets:
            return self._datasets[dataset_id]

        dataset_dir = os.path.join(self.base_dir, dataset_id)
        bars_path = os.path.join(dataset_dir, "bars.jsonl")
        manifest_path = os.path.join(dataset_dir, "manifest.json")

        if os.path.exists(bars_path):
            try:
                bars: List[MarketDataEvent] = []
                with open(bars_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        r = json.loads(line)
                        t = datetime.fromisoformat(r["event_time"])
                        if t.tzinfo is None:
                            t = t.replace(tzinfo=timezone.utc)
                        bar = MarketDataEvent(
                            event_id=r.get("event_id", f"mde_{uuid.uuid4().hex[:12]}"),
                            symbol=r["symbol"],
                            asset_class=r.get("asset_class", "STOCKS"),
                            timeframe=r.get("timeframe", "1m"),
                            event_time=t,
                            timestamp=t,
                            ingest_time=t,
                            open=r["open"],
                            high=r["high"],
                            low=r["low"],
                            close=r["close"],
                            volume=r["volume"],
                            trade_count=r.get("trade_count", 0),
                            vwap=r.get("vwap", 0.0),
                            bar_revision=r.get("bar_revision", 0),
                            is_final=r.get("is_final", True),
                            provenance=r.get("provenance", "REAL_HISTORICAL_MARKET_DATA"),
                            environment=r.get("environment", "SIMULATION"),
                        )
                        bars.append(bar)

                self._datasets[dataset_id] = bars

                if os.path.exists(manifest_path):
                    with open(manifest_path, "r", encoding="utf-8") as mf:
                        m_data = json.load(mf)
                        self._manifests[dataset_id] = DatasetManifest.from_dict(m_data)

                logger.info(f"Loaded dataset '{dataset_id}' ({len(bars)} bars) from disk cache {dataset_dir}")
                return bars
            except Exception as e:
                logger.error(f"Error reading dataset files from {dataset_dir}: {e}")
                return None

        return None

    def get_dataset(self, dataset_id: str) -> Optional[List[MarketDataEvent]]:
        """Returns the sorted bar list for a registered dataset (checking memory and disk)."""
        return self.load_dataset(dataset_id)

    def get_manifest(self, dataset_id: str) -> Optional[DatasetManifest]:
        """Returns the manifest for a dataset, loading from disk if necessary."""
        if dataset_id in self._manifests:
            return self._manifests[dataset_id]

        manifest_path = os.path.join(self.base_dir, dataset_id, "manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as mf:
                    m_data = json.load(mf)
                    manifest = DatasetManifest.from_dict(m_data)
                    self._manifests[dataset_id] = manifest
                    return manifest
            except Exception as e:
                logger.warning(f"Failed to load manifest for '{dataset_id}': {e}")
        return None

    def list_manifests(self) -> List[DatasetManifest]:
        """Lists all manifests available in memory or cached on disk."""
        manifests_by_id: Dict[str, DatasetManifest] = dict(self._manifests)

        if os.path.exists(self.base_dir):
            for entry in os.listdir(self.base_dir):
                target_manifest = os.path.join(self.base_dir, entry, "manifest.json")
                if entry not in manifests_by_id and os.path.isfile(target_manifest):
                    try:
                        with open(target_manifest, "r", encoding="utf-8") as mf:
                            m_data = json.load(mf)
                            m = DatasetManifest.from_dict(m_data)
                            manifests_by_id[m.dataset_id] = m
                    except Exception as e:
                        logger.debug(f"Could not load manifest from {target_manifest}: {e}")

        return list(manifests_by_id.values())

    def find_cached_dataset(
        self,
        symbol: str,
        timeframe: str,
        feed: str,
        start_time: datetime,
        end_time: datetime,
        adjustment_policy: str = "RAW",
    ) -> Optional[DatasetManifest]:
        """
        Searches available cached datasets for one that covers the requested window and parameters.
        Returns the matching DatasetManifest or None.
        """
        sym_clean = symbol.upper()
        req_start_iso = start_time.isoformat()
        req_end_iso = end_time.isoformat()
        feed_upper = feed.upper()

        for m in self.list_manifests():
            if m.is_synthetic:
                continue
            if sym_clean in m.symbols and m.timeframe == timeframe:
                if m.feed.upper() == feed_upper and m.adjustment_policy == adjustment_policy:
                    # Check if requested window is satisfied
                    if (m.requested_start == req_start_iso and m.requested_end == req_end_iso) or (
                        m.start_time <= req_start_iso and m.end_time >= req_end_iso
                    ):
                        return m
        return None

    def export_csv(self, dataset_id: str, output_path: Optional[str] = None) -> str:
        """
        Exports a dataset's bars into a standard CSV file.
        Returns the output file path.
        """
        bars = self.load_dataset(dataset_id)
        if not bars:
            raise ValueError(f"Dataset '{dataset_id}' not found")

        if not output_path:
            output_path = os.path.join(self.base_dir, dataset_id, f"{dataset_id}.csv")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("timestamp,symbol,open,high,low,close,volume,trade_count,vwap\n")
            for b in bars:
                f.write(
                    f"{b.event_time.isoformat()},{b.symbol},{float(b.open):.4f},{float(b.high):.4f},"
                    f"{float(b.low):.4f},{float(b.close):.4f},{float(b.volume):.2f},"
                    f"{getattr(b, 'trade_count', 0)},{float(getattr(b, 'vwap', 0.0)):.4f}\n"
                )
        return output_path

    @staticmethod
    def _classify_gap(
        cur_utc: datetime,
        nxt_utc: datetime,
        asset_class: str,
        diff_sec: float,
    ) -> Tuple[str, str]:
        """Classifies a gap between consecutive bars without altering or fabricating bars."""
        if asset_class.upper() == "CRYPTO":
            return "FEED_GAP", "Crypto 24/7 missing interval"

        cur_ny = cur_utc.astimezone(_NY_TZ)
        nxt_ny = nxt_utc.astimezone(_NY_TZ)
        cur_sess = HistoricalDatasetManager.classify_market_session(cur_utc, asset_class)
        nxt_sess = HistoricalDatasetManager.classify_market_session(nxt_utc, asset_class)

        if cur_ny.date() != nxt_ny.date() or diff_sec >= 3600 or cur_sess == "CLOSED" or nxt_sess == "CLOSED":
            return "NON_TRADING_SESSION", f"Overnight/weekend/holiday transition ({cur_sess} -> {nxt_sess})"

        if cur_sess in ("PRE_MARKET", "AFTER_HOURS") or nxt_sess in ("PRE_MARKET", "AFTER_HOURS"):
            return "EXTENDED_HOURS_NO_TRADE", f"Sparse extended-hours IEX/venue activity ({cur_sess})"

        return "RTH_NO_TRADE_OR_MISSING", "Missing 1m bar during regular session (no print or feed gap)"

    @staticmethod
    def detect_gaps(
        bars: List[MarketDataEvent],
        expected_step_minutes: int = 1,
        expected_interval_seconds: Optional[int] = None,
        asset_classes: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Detects missing intervals between consecutive bars for the same symbol.
        Does not interpolate or invent bars silently; returns diagnostic gap report
        with session-aware classification (NON_TRADING_SESSION vs EXTENDED_HOURS_NO_TRADE vs RTH).
        """
        bars_by_symbol: Dict[str, List[MarketDataEvent]] = {}
        for b in bars:
            bars_by_symbol.setdefault(b.symbol, []).append(b)

        gaps: List[Dict[str, Any]] = []
        expected_sec = expected_interval_seconds if expected_interval_seconds is not None else (expected_step_minutes * 60)
        for sym, sym_bars in bars_by_symbol.items():
            sym_bars_sorted = sorted(sym_bars, key=lambda x: x.event_time)
            inferred_ac = "CRYPTO" if "/" in sym else "STOCKS"
            sym_ac = (asset_classes or {}).get(sym) or getattr(sym_bars_sorted[0], "asset_class", None) or inferred_ac
            for i in range(len(sym_bars_sorted) - 1):
                cur = sym_bars_sorted[i].event_time
                nxt = sym_bars_sorted[i + 1].event_time
                cur_utc = (cur if cur.tzinfo is not None else cur.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
                nxt_utc = (nxt if nxt.tzinfo is not None else nxt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
                diff_sec = (nxt_utc - cur_utc).total_seconds()
                if diff_sec > expected_sec:
                    missing_bars = int(diff_sec // expected_sec) - 1
                    gap_type, session_context = HistoricalDatasetManager._classify_gap(
                        cur_utc, nxt_utc, sym_ac, diff_sec
                    )
                    gaps.append({
                        "symbol": sym,
                        "gap_start": cur_utc.isoformat(),
                        "gap_end": nxt_utc.isoformat(),
                        "gap_duration_seconds": diff_sec,
                        "gap_seconds": diff_sec,
                        "missing_bars_estimated": missing_bars,
                        "gap_type": gap_type,
                        "session_context": session_context,
                    })

        return gaps

    @staticmethod
    def summarize_gaps(gaps: List[Dict[str, Any]]) -> Dict[str, int]:
        """Counts detected gaps grouped by session-aware gap_type."""
        counts = {
            "total_gaps": len(gaps),
            "non_trading_session": 0,
            "extended_hours_no_trade": 0,
            "rth_missing": 0,
            "feed_gap": 0,
        }
        for g in gaps:
            gtype = g.get("gap_type", "")
            if gtype == "NON_TRADING_SESSION":
                counts["non_trading_session"] += 1
            elif gtype == "EXTENDED_HOURS_NO_TRADE":
                counts["extended_hours_no_trade"] += 1
            elif gtype == "FEED_GAP":
                counts["feed_gap"] += 1
            else:
                counts["rth_missing"] += 1
        return counts

    def load_from_jsonl(
        self,
        filepath: str,
        dataset_id: Optional[str] = None,
        version: str = "1.0.0",
    ) -> Tuple[List[MarketDataEvent], DatasetManifest]:
        """Loads and normalizes raw JSONL bars into a registered dataset."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Dataset file not found: {filepath}")

        d_id = dataset_id or os.path.splitext(os.path.basename(filepath))[0]
        raw_bars: List[MarketDataEvent] = []

        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                mde = MarketDataNormalizer.normalize_raw(
                    topic="historical-dataset",
                    payload=record,
                    provenance="HISTORICAL_BACKFILL",
                )
                raw_bars.append(mde)

        return self.create_dataset_from_bars(dataset_id=d_id, bars=raw_bars, version=version)
