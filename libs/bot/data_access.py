"""
libs/bot/data_access.py — Strategy-Facing Data Access Interface (GĐ30)
Decouples Strategy Engine (GĐ31) from Kafka / Redpanda clients.
Provides subscribe, get_latest_bar, get_historical_bars, replay, get_data_quality, and health checks.
"""

from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timezone

from libs.bot.domain import MarketDataEvent
from libs.bot.consumer import PaperBotConsumer
from libs.bot.storage import MarketDataStore
from libs.bot.quality import DataQualityEngine
from libs.bot.revision import BarRevisionManager
from libs.bot.observability import DataTelemetryCollector
from libs.bot.backfill import HistoricalBackfillManager


class PaperBotDataAccess:
    """
    Standard Data Access Layer interface for Paper Trading Bot V2.
    The Strategy Engine (GĐ31) relies entirely on this class, having zero direct Kafka dependencies.
    """

    def __init__(
        self,
        consumer: Optional[PaperBotConsumer] = None,
        store: Optional[MarketDataStore] = None,
        quality_engine: Optional[DataQualityEngine] = None,
        revision_manager: Optional[BarRevisionManager] = None,
        backfill_manager: Optional[HistoricalBackfillManager] = None,
        telemetry: Optional[DataTelemetryCollector] = None,
    ):
        self.store = store or MarketDataStore()
        self.quality = quality_engine or DataQualityEngine()
        self.revision = revision_manager or BarRevisionManager(final_only=True)
        self.telemetry = telemetry or DataTelemetryCollector()
        self.backfill = backfill_manager or HistoricalBackfillManager(store=self.store)

        self.consumer = consumer or PaperBotConsumer(
            store=self.store,
            telemetry=self.telemetry,
            quality_engine=self.quality,
            revision_manager=self.revision,
            use_mock_transport=True,
        )

        # Internal cache of latest bar per symbol
        self._latest_bars: Dict[str, MarketDataEvent] = {}
        # Subscriber callbacks: list of callbacks
        self._subscribers: List[Callable[[MarketDataEvent], None]] = []

        # Wire consumer to internal update
        self.consumer.subscribe_callback(self._on_consumer_bar)

    def _on_consumer_bar(self, bar: MarketDataEvent) -> None:
        """Internal router caching latest bar and notifying subscribers."""
        self._latest_bars[bar.symbol] = bar
        for cb in self._subscribers:
            try:
                cb(bar)
            except Exception as e:
                pass

    def subscribe(
        self,
        symbols: List[str],
        timeframe: str = "1m",
        callback: Optional[Callable[[MarketDataEvent], None]] = None,
    ) -> None:
        """Registers a strategy callback for 1-minute bars."""
        if timeframe != "1m":
            raise ValueError(f"Unsupported timeframe '{timeframe}'. Only '1m' is supported in V2 Data Layer.")
        if callback:
            self._subscribers.append(callback)

    def get_latest_bar(self, symbol: str) -> Optional[MarketDataEvent]:
        """Returns most recent 1m bar for symbol."""
        # 1. From internal live cache
        if symbol in self._latest_bars:
            return self._latest_bars[symbol]

        # 2. From revision active bars
        for k, bar in self.revision.get_all_active_bars().items():
            if bar.symbol == symbol:
                return bar

        # 3. From persistent store
        bars = self.store.load_bars(symbol)
        if bars:
            return bars[-1]

        return None

    def get_historical_bars(
        self,
        symbol: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[MarketDataEvent]:
        """Retrieves historical bars from persistent store."""
        return self.store.load_bars(symbol, start=start, end=end)

    def replay(
        self,
        start: datetime,
        end: datetime,
        symbols: List[str],
        on_bar_callback: Callable[[MarketDataEvent], None],
    ) -> int:
        """
        Replays historical bars for given symbols between start and end in chronological event-time order.
        Returns total bars replayed.
        """
        all_bars: List[MarketDataEvent] = []
        for sym in symbols:
            bars = self.get_historical_bars(sym, start=start, end=end)
            all_bars.extend(bars)

        return self.backfill.replay_bars(all_bars, on_bar_callback)

    def get_data_quality(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Returns data quality report summary."""
        summary = self.quality.get_quality_summary()
        if symbol:
            summary["symbol_filtered"] = symbol
        return summary

    def get_consumer_health(self) -> Dict[str, Any]:
        """Returns health status of the ingestion consumer."""
        return self.consumer.get_health()

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns ingestion telemetry metrics."""
        return self.telemetry.get_telemetry_snapshot()
