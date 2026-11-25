"""
libs/bot/orchestration/lifecycle.py — Bot Lifecycle State Machine (GĐ34)
Defines lifecycle states, allowed transitions, error management, and audit events.
"""

from typing import Set, Dict, Optional
from datetime import datetime, timezone
import uuid
import logging

from libs.bot.domain import BotSession, BotAuditEvent

logger = logging.getLogger("bot-lifecycle")


class BotLifecycleState:
    """Standardized bot lifecycle states for AlgoTrading V2.0."""
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"
    DATA_GAP_BLOCKED = "DATA_GAP_BLOCKED"


TERMINAL_STATES: Set[str] = {
    BotLifecycleState.STOPPED,
}

ACTIVE_STATES: Set[str] = {
    BotLifecycleState.STARTING,
    BotLifecycleState.RUNNING,
    BotLifecycleState.PAUSED,
    BotLifecycleState.STOPPING,
    BotLifecycleState.DATA_GAP_BLOCKED,
}


class InvalidLifecycleStateTransitionError(Exception):
    """Raised when an illegal bot lifecycle state transition is attempted."""
    pass


class BotLifecycleStateMachine:
    """
    Enforces deterministic lifecycle transitions and maintains audit records.
    """

    VALID_TRANSITIONS: Dict[str, Set[str]] = {
        BotLifecycleState.STARTING: {
            BotLifecycleState.RUNNING,
            BotLifecycleState.ERROR,
            BotLifecycleState.STOPPING,
        },
        BotLifecycleState.RUNNING: {
            BotLifecycleState.PAUSED,
            BotLifecycleState.STOPPING,
            BotLifecycleState.ERROR,
            BotLifecycleState.DATA_GAP_BLOCKED,
        },
        BotLifecycleState.PAUSED: {
            BotLifecycleState.RUNNING,
            BotLifecycleState.STOPPING,
            BotLifecycleState.ERROR,
            BotLifecycleState.DATA_GAP_BLOCKED,
        },
        BotLifecycleState.DATA_GAP_BLOCKED: {
            BotLifecycleState.RUNNING,
            BotLifecycleState.STOPPING,
            BotLifecycleState.ERROR,
        },
        BotLifecycleState.STOPPING: {
            BotLifecycleState.STOPPED,
            BotLifecycleState.ERROR,
        },
        BotLifecycleState.ERROR: {
            BotLifecycleState.STOPPING,
            BotLifecycleState.STOPPED,
        },
        BotLifecycleState.STOPPED: {
            BotLifecycleState.STARTING,
        },
    }

    @classmethod
    def can_transition(cls, current_state: str, new_state: str) -> bool:
        """Checks if a transition between two states is permitted."""
        allowed = cls.VALID_TRANSITIONS.get(current_state, set())
        return new_state in allowed

    @classmethod
    def transition(
        cls,
        session: BotSession,
        new_state: str,
        reason: str = "",
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> BotAuditEvent:
        """
        Executes a validated lifecycle state transition.
        Raises InvalidLifecycleStateTransitionError if illegal.
        Returns a BotAuditEvent for persistence.
        """
        curr = session.lifecycle_state

        # Idempotency check: Transitioning to the exact same state is a no-op
        if curr == new_state:
            logger.debug(f"Session {session.bot_session_id} is already in state '{curr}'. Idempotent no-op.")
            return BotAuditEvent(
                component="LIFECYCLE_CONTROLLER",
                event_type="STATE_UNCHANGED",
                reason=f"Already in state {curr}",
                payload={"session_id": session.bot_session_id, "state": curr},
                environment="SIMULATION",
            )

        if curr in TERMINAL_STATES and new_state not in cls.VALID_TRANSITIONS.get(curr, set()):
            raise InvalidLifecycleStateTransitionError(
                f"Cannot transition session {session.bot_session_id} out of terminal state '{curr}' to '{new_state}'"
            )

        if not cls.can_transition(curr, new_state):
            raise InvalidLifecycleStateTransitionError(
                f"Illegal lifecycle transition for session {session.bot_session_id}: '{curr}' -> '{new_state}'"
            )

        now = datetime.now(timezone.utc)
        session.lifecycle_state = new_state
        session.status = new_state
        session.updated_at = now

        if new_state == BotLifecycleState.RUNNING and not session.started_at:
            session.started_at = now
            session.start_time = now
        elif new_state == BotLifecycleState.PAUSED:
            session.paused_at = now
        elif new_state == BotLifecycleState.STOPPED:
            session.stopped_at = now
            session.end_time = now
        elif new_state == BotLifecycleState.ERROR:
            session.error_code = error_code or "UNSPECIFIED_ERROR"
            session.error_message = error_message or reason

        audit_event = BotAuditEvent(
            event_id=f"aud_lc_{uuid.uuid4().hex[:10]}",
            timestamp=now,
            component="BOT_LIFECYCLE_CONTROLLER",
            event_type="LIFECYCLE_STATE_TRANSITION",
            trace_id=f"trace_lc_{uuid.uuid4().hex[:8]}",
            reason=reason or f"Transition from {curr} to {new_state}",
            payload={
                "session_id": session.bot_session_id,
                "old_state": curr,
                "new_state": new_state,
                "error_code": session.error_code,
                "error_message": session.error_message,
            },
            environment="SIMULATION",
        )
        logger.info(f"Bot session {session.bot_session_id} transitioned: {curr} -> {new_state} ({reason})")
        return audit_event
