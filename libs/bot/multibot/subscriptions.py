"""
libs/bot/multibot/subscriptions.py — Multi-Bot Market Data Subscription Manager (GĐ37)
Tracks symbol and timeframe subscriptions per bot for fan-out routing.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, List, Optional
import logging

logger = logging.getLogger("multibot-subscriptions")


@dataclass
class BotSubscription:
    """Represents a bot's market data subscription configuration."""
    bot_id: str
    symbols: Set[str] = field(default_factory=set)
    timeframe: str = "1m"
    asset_classes: Dict[str, str] = field(default_factory=dict)
    is_active: bool = True

    def matches(self, symbol: str, timeframe: str = "1m") -> bool:
        """Checks if this subscription covers the given symbol and timeframe."""
        if not self.is_active:
            return False
        return symbol in self.symbols and self.timeframe == timeframe


class SubscriptionManager:
    """
    Manages market data subscriptions for all registered bots.
    Provides fast indexed lookup by (symbol, timeframe).
    """

    def __init__(self):
        # bot_id -> BotSubscription
        self._subscriptions: Dict[str, BotSubscription] = {}
        # (symbol, timeframe) -> Set[bot_id]
        self._symbol_index: Dict[tuple, Set[str]] = {}

    def register_subscription(self, subscription: BotSubscription) -> None:
        """Registers or replaces a bot's market data subscription."""
        # Clean existing index entries if replacing
        if subscription.bot_id in self._subscriptions:
            self.remove_subscription(subscription.bot_id)

        self._subscriptions[subscription.bot_id] = subscription
        self._rebuild_index_for_bot(subscription)
        logger.info(
            f"Registered subscription for bot '{subscription.bot_id}': "
            f"symbols={list(subscription.symbols)}, timeframe={subscription.timeframe}"
        )

    def update_subscription(
        self,
        bot_id: str,
        symbols: Optional[Set[str]] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[BotSubscription]:
        """Updates symbol set or active status for a bot subscription."""
        sub = self._subscriptions.get(bot_id)
        if not sub:
            return None

        if symbols is not None:
            sub.symbols = set(symbols)
        if is_active is not None:
            sub.is_active = is_active

        self._rebuild_index_for_bot(sub)
        return sub

    def remove_subscription(self, bot_id: str) -> bool:
        """Removes a bot's subscription and clears indexed entries."""
        sub = self._subscriptions.pop(bot_id, None)
        if not sub:
            return False

        for (sym, tf), bots in list(self._symbol_index.items()):
            bots.discard(bot_id)
            if not bots:
                self._symbol_index.pop((sym, tf), None)

        logger.info(f"Removed subscription for bot '{bot_id}'")
        return True

    def _rebuild_index_for_bot(self, sub: BotSubscription) -> None:
        """Updates internal index for a single subscription."""
        # Clear old index entries for this bot
        for bots in self._symbol_index.values():
            bots.discard(sub.bot_id)

        if not sub.is_active:
            return

        for sym in sub.symbols:
            key = (sym, sub.timeframe)
            if key not in self._symbol_index:
                self._symbol_index[key] = set()
            self._symbol_index[key].add(sub.bot_id)

    def get_subscribed_bots(self, symbol: str, timeframe: str = "1m") -> List[str]:
        """Returns list of active bot IDs subscribed to the symbol and timeframe."""
        key = (symbol, timeframe)
        bots = self._symbol_index.get(key, set())
        return sorted(list(bots))

    def is_bot_subscribed(self, bot_id: str, symbol: str, timeframe: str = "1m") -> bool:
        """Checks whether a specific bot is actively subscribed to a symbol."""
        sub = self._subscriptions.get(bot_id)
        if not sub:
            return False
        return sub.matches(symbol, timeframe)

    def get_subscription(self, bot_id: str) -> Optional[BotSubscription]:
        """Retrieves subscription by bot ID."""
        return self._subscriptions.get(bot_id)

    def list_all_subscriptions(self) -> Dict[str, BotSubscription]:
        """Returns all subscriptions."""
        return dict(self._subscriptions)
