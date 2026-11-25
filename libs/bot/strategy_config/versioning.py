"""
libs/bot/strategy_config/versioning.py — Deterministic Canonical Serializer & Hash Engine (GĐ38)
Ensures reproducible, bitwise-identical SHA-256 hashing of strategy configurations and presets.
"""

from typing import Any, Dict
import hashlib
import json


def canonical_serialize(data: Any) -> str:
    """
    Deterministically serializes any configuration dict or structure into canonical JSON.
    - Keys are recursively sorted.
    - Floats are rounded/formatted to avoid IEEE 754 precision discrepancies where appropriate.
    - No unnecessary whitespace.
    """
    def _normalize(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _normalize(v) for k, v in sorted(obj.items())}
        elif isinstance(obj, (list, tuple)):
            return [_normalize(item) for item in obj]
        elif isinstance(obj, float):
            # Format cleanly to max 8 decimal places if float
            return round(obj, 8)
        else:
            return obj

    normalized = _normalize(data)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_configuration_hash(data: Any) -> str:
    """
    Calculates the SHA-256 hex digest of the canonical serialization of the input data.
    """
    canon = canonical_serialize(data)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()
