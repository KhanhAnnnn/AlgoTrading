"""
libs/bot/orchestration — Bot Core Orchestration & Lifecycle Controller (GĐ34)
Provides lifecycle state management, event loop, checkpoints, recovery,
health monitoring, performance reporting, and command service for AlgoTrading V2.0.
"""

from libs.bot.orchestration.lifecycle import (
    BotLifecycleState,
    TERMINAL_STATES as LIFECYCLE_TERMINAL_STATES,
    ACTIVE_STATES as LIFECYCLE_ACTIVE_STATES,
    InvalidLifecycleStateTransitionError,
    BotLifecycleStateMachine,
)
from libs.bot.orchestration.stop_policy import StopPolicy
from libs.bot.orchestration.session import SessionStore
from libs.bot.orchestration.event_journal import BotEventJournal
from libs.bot.orchestration.checkpoint import (
    BotCheckpoint,
    BotCheckpointManager,
)
from libs.bot.orchestration.health import BotHealthMonitor
from libs.bot.orchestration.performance import BotPerformanceReporter
from libs.bot.orchestration.recovery import BotRecoveryManager
from libs.bot.orchestration.event_loop import (
    QueueOverflowError,
    BotEventLoop,
)
from libs.bot.orchestration.orchestrator import BotOrchestrator
from libs.bot.orchestration.command_service import BotCommandService

__all__ = [
    "BotLifecycleState",
    "LIFECYCLE_TERMINAL_STATES",
    "LIFECYCLE_ACTIVE_STATES",
    "InvalidLifecycleStateTransitionError",
    "BotLifecycleStateMachine",
    "StopPolicy",
    "SessionStore",
    "BotEventJournal",
    "BotCheckpoint",
    "BotCheckpointManager",
    "BotHealthMonitor",
    "BotPerformanceReporter",
    "BotRecoveryManager",
    "QueueOverflowError",
    "BotEventLoop",
    "BotOrchestrator",
    "BotCommandService",
]
