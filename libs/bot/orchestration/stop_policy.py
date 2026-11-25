"""
libs/bot/orchestration/stop_policy.py — Bot Shutdown Stop Policy (GĐ34)
Defines behavior for open simulation orders when stopping a bot session.
"""

from enum import Enum


class StopPolicy(str, Enum):
    """
    Policy determining how active simulation orders are handled upon shutdown.
    """
    CANCEL_REMAINDER = "CANCEL_REMAINDER"  # Cancels open orders and releases reserved cash (recommended default)
    KEEP_WORKING = "KEEP_WORKING"          # Leaves orders working in simulation broker but freezes fills
