"""
libs/bot/experiments/__init__.py — Experiment Management, Comparability & Robustness Package (GĐ38)
"""

from libs.bot.experiments.calendar import MarketSessionCalendar, EASTERN_TZ
from libs.bot.experiments.fingerprint import EconomicSequenceFingerprint
from libs.bot.experiments.comparability import ComparabilityEngine, ComparabilityResult
from libs.bot.experiments.comparison import BacktestComparisonService
from libs.bot.experiments.robustness import StrategyRobustnessAnalyzer
from libs.bot.experiments.store import ExperimentStore
from libs.bot.experiments.manager import (
    BacktestExperiment,
    ExperimentVariant,
    BacktestExperimentManager,
)

__all__ = [
    "MarketSessionCalendar",
    "EASTERN_TZ",
    "EconomicSequenceFingerprint",
    "ComparabilityEngine",
    "ComparabilityResult",
    "BacktestComparisonService",
    "StrategyRobustnessAnalyzer",
    "ExperimentStore",
    "BacktestExperiment",
    "ExperimentVariant",
    "BacktestExperimentManager",
]
