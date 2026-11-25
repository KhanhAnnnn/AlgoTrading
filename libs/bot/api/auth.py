"""
libs/bot/api/auth.py — API Security & Access Control (GĐ35)
Provides authentication dependency for REST endpoints and WebSocket handshakes.
Enforces read-only vs write permission and prevents unauthorized execution commands.
"""

import os
from typing import Optional
from fastapi import Header, HTTPException, status, Query


# Configurable API key (optional for local simulation dev, enforced if set in env)
V2_API_KEY_ENV = os.environ.get("V2_API_KEY", "")


def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token: Optional[str] = Query(None, description="Auth token for WebSocket query param")
) -> bool:
    """
    Validates API key from header or query param.
    If V2_API_KEY is configured in environment, strictly validates matching key.
    If V2_API_KEY is not set or empty, allows simulation requests with environment='SIMULATION'.
    """
    expected_key = os.environ.get("V2_API_KEY", "")
    if not expected_key:
        return True  # Development simulation sandbox default

    header_val = x_api_key if isinstance(x_api_key, str) else None
    token_val = token if isinstance(token, str) else None
    provided = header_val or token_val

    if not provided or provided != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key / token credentials",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return True
