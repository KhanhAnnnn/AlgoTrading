"""
libs/bot/multibot — AlgoTrading V2.0 Multi-Bot Management & Supervisor Package (GĐ37)
"""

from libs.bot.multibot.resource_policy import ResourcePolicy
from libs.bot.multibot.registry import BotDefinition, BotRegistry
from libs.bot.multibot.subscriptions import BotSubscription, SubscriptionManager
from libs.bot.multibot.dispatcher import V2MarketDataDispatcher, QueueOverflowError
from libs.bot.multibot.isolation import (
    BotSandboxFactory,
    get_bot_storage_dir,
    get_bot_order_store_dir,
    get_bot_fill_store_dir,
    get_bot_checkpoint_dir,
    get_bot_journal_dir,
)
from libs.bot.multibot.supervisor import (
    MultiBotSupervisor,
    BotRuntime,
    ConcurrencyLimitExceededError,
    BotNotFoundError,
)
from libs.bot.multibot.recovery import MultiBotRecoveryManager
from libs.bot.multibot.telemetry import SupervisorTelemetryCollector

__all__ = [
    "ResourcePolicy",
    "BotDefinition",
    "BotRegistry",
    "BotSubscription",
    "SubscriptionManager",
    "V2MarketDataDispatcher",
    "QueueOverflowError",
    "BotSandboxFactory",
    "get_bot_storage_dir",
    "get_bot_order_store_dir",
    "get_bot_fill_store_dir",
    "get_bot_checkpoint_dir",
    "get_bot_journal_dir",
    "MultiBotSupervisor",
    "BotRuntime",
    "ConcurrencyLimitExceededError",
    "BotNotFoundError",
    "MultiBotRecoveryManager",
    "SupervisorTelemetryCollector",
]
