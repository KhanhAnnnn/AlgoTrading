"""
libs/bot/indicators/result.py — Structured Indicator Output (GĐ31)
Defines uniform IndicatorResult representing indicator calculations with complete provenance.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional


@dataclass
class IndicatorResult:
    """
    Uniform result structure for all technical indicators.
    Guarantees explicit warmup tracking, parameter capture, and traceability.
    """
    indicator_id: str
    indicator_version: str
    symbol: str
    timeframe: str = "1m"
    event_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    value: Any = None  # float, Dict[str, float], or None if warmup incomplete
    parameters: Dict[str, Any] = field(default_factory=dict)
    warmup_complete: bool = False
    data_quality_status: str = "VALID"
    source_bar_revision: int = 0
