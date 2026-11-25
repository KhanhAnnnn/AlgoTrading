"""
libs/bot/api/routes.py — FastAPI REST & WebSocket Routes (GĐ35)
Implements all /api/v2/bots REST endpoints and /ws/v2/bots WebSocket streaming.
"""

import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Path, WebSocket, WebSocketDisconnect, status

from libs.bot.api.schemas import (
    CreateBotRequest,
    BotControlRequest,
    SubmitBarRequest,
    BotSummaryResponse,
    PortfolioResponse,
    OrderResponse,
    FillResponse,
    PerformanceResponse,
    HealthResponse,
)
from libs.bot.api.service import bot_api_service, BotApiService
from libs.bot.api.websocket import ws_manager
from libs.bot.api.auth import verify_api_key

router = APIRouter(prefix="/api/v2/bots", tags=["V2 Paper Trading Bots"])
ws_router = APIRouter(tags=["V2 WebSockets"])


@router.get("", response_model=List[BotSummaryResponse], summary="List all Paper Trading Bots")
def list_bots(
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves all active and persisted V2 Paper Trading Bot sessions."""
    return bot_api_service.list_bots()


@router.post("", response_model=BotSummaryResponse, status_code=status.HTTP_201_CREATED, summary="Create a new Paper Trading Bot")
def create_bot(
    req: CreateBotRequest,
    authorized: bool = Depends(verify_api_key),
):
    """Creates and initializes a new isolated Paper Trading Bot session."""
    r_config_dict = req.risk_config.dict() if req.risk_config else None
    try:
        summary = bot_api_service.create_bot(
            bot_id=req.bot_id,
            bot_name=req.bot_name,
            symbols=req.symbols,
            timeframe=req.timeframe,
            initial_cash=req.initial_cash,
            strategy_id=req.strategy_id,
            strategy_version=req.strategy_version,
            risk_config_dict=r_config_dict,
            stop_policy_str=req.stop_policy,
        )
        return summary
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/overview", summary="Get Multi-Bot Supervisor Overview")
def get_supervisor_overview(
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves aggregated multi-bot supervisor telemetry, system health, and concurrency stats."""
    return bot_api_service.get_supervisor_overview()


@router.post("/dispatch_bar", summary="Fan-out Market Data Bar to Subscribed Bots")
def dispatch_bar(
    req: SubmitBarRequest = ...,
    authorized: bool = Depends(verify_api_key),
):
    """Dispatches a market data event to all subscribed bots through the supervisor."""
    if req.environment != "SIMULATION":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Security error: environment must be strictly 'SIMULATION'",
        )
    return bot_api_service.dispatch_bar(req.dict())


@router.get("/{session_id}", response_model=BotSummaryResponse, summary="Get Bot details")
def get_bot(
    session_id: str = Path(..., description="Bot session ID or bot ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Returns aggregated status and metadata for a specific bot."""
    bot = bot_api_service.get_bot(session_id)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot '{session_id}' not found")
    return bot


@router.post("/{session_id}/start", response_model=BotSummaryResponse, summary="Start a Bot session")
def start_bot(
    session_id: str = Path(..., description="Bot session ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Transitions bot state to RUNNING and enables the 1m event loop."""
    try:
        return bot_api_service.start_bot(session_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot '{session_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{session_id}/pause", response_model=BotSummaryResponse, summary="Pause a Bot session")
def pause_bot(
    session_id: str = Path(..., description="Bot session ID"),
    req: Optional[BotControlRequest] = None,
    authorized: bool = Depends(verify_api_key),
):
    """Pauses event loop processing while preserving active working simulation orders."""
    reason = req.reason if req and req.reason else "OPERATOR_PAUSE"
    try:
        return bot_api_service.pause_bot(session_id, reason=reason)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot '{session_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{session_id}/resume", response_model=BotSummaryResponse, summary="Resume a paused Bot session")
def resume_bot(
    session_id: str = Path(..., description="Bot session ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Resumes event loop processing for a paused bot session."""
    try:
        return bot_api_service.resume_bot(session_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot '{session_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{session_id}/stop", response_model=BotSummaryResponse, summary="Gracefully stop a Bot session")
def stop_bot(
    session_id: str = Path(..., description="Bot session ID"),
    req: Optional[BotControlRequest] = None,
    authorized: bool = Depends(verify_api_key),
):
    """Gracefully shuts down bot session and applies StopPolicy (CANCEL_REMAINDER or KEEP_WORKING)."""
    policy = req.policy if req and req.policy else None
    try:
        return bot_api_service.stop_bot(session_id, policy_str=policy)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot '{session_id}' not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{session_id}/sessions", summary="Get Bot Sessions")
def get_bot_sessions(
    session_id: str = Path(..., description="Bot ID or session ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves all past and active sessions for a specific bot."""
    return bot_api_service.list_bot_sessions(session_id)


@router.post("/{session_id}/archive", summary="Archive Bot Definition")
def archive_bot(
    session_id: str = Path(..., description="Bot ID to archive"),
    authorized: bool = Depends(verify_api_key),
):
    """Soft-archives a bot definition while preserving historical sessions and audit trails."""
    try:
        archived = bot_api_service.archive_bot(session_id)
        if not archived:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot '{session_id}' not found")
        return {"status": "ARCHIVED", "bot_id": session_id}
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot '{session_id}' not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{session_id}/portfolio", response_model=PortfolioResponse, summary="Get Bot Portfolio")
def get_bot_portfolio(
    session_id: str = Path(..., description="Bot session ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves real-time cash, reserved buying power, equity, and simulated open positions."""
    port = bot_api_service.get_portfolio(session_id)
    if not port:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Portfolio for bot '{session_id}' not found")
    return port


@router.get("/{session_id}/orders", response_model=List[OrderResponse], summary="Get Bot Orders")
def get_bot_orders(
    session_id: str = Path(..., description="Bot session ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: WORKING, FILLED, CANCELLED"),
    symbol_filter: Optional[str] = Query(None, alias="symbol", description="Filter by symbol"),
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves simulated orders placed by this bot."""
    bot = bot_api_service.get_bot(session_id)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot '{session_id}' not found")
    return bot_api_service.get_orders(session_id, status_filter=status_filter, symbol_filter=symbol_filter)


@router.get("/{session_id}/fills", response_model=List[FillResponse], summary="Get Bot Fills")
def get_bot_fills(
    session_id: str = Path(..., description="Bot session ID"),
    symbol_filter: Optional[str] = Query(None, alias="symbol", description="Filter by symbol"),
    limit: int = Query(100, ge=1, le=1000, description="Max fills to return"),
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves execution fill records for this bot."""
    bot = bot_api_service.get_bot(session_id)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot '{session_id}' not found")
    return bot_api_service.get_fills(session_id, symbol_filter=symbol_filter, limit=limit)


@router.get("/{session_id}/performance", response_model=PerformanceResponse, summary="Get Bot Performance Analytics")
def get_bot_performance(
    session_id: str = Path(..., description="Bot session ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves quantitative performance metrics, PnL, drawdown, and signal conversion funnel."""
    perf = bot_api_service.get_performance(session_id)
    if not perf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Performance report for bot '{session_id}' not found")
    return perf


@router.get("/{session_id}/health", response_model=HealthResponse, summary="Get Bot Health Status")
def get_bot_health(
    session_id: str = Path(..., description="Bot session ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves heartbeat, latency, queue depth, and feed staleness monitoring status."""
    health = bot_api_service.get_health(session_id)
    if not health:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Health status for bot '{session_id}' not found")
    return health


@router.post("/{session_id}/bars", summary="Submit a 1m bar to Bot Event Loop")
def submit_bar(
    session_id: str = Path(..., description="Bot session ID"),
    req: SubmitBarRequest = ...,
    authorized: bool = Depends(verify_api_key),
):
    """Submits a finalized 1m bar directly into the bot event loop for immediate execution."""
    if req.environment != "SIMULATION":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Security error: environment must be strictly 'SIMULATION'",
        )
    try:
        return bot_api_service.submit_bar(session_id, req.dict())
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot '{session_id}' not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ==============================================================================
# WEBSOCKET STREAMING ENDPOINTS
# ==============================================================================

@ws_router.websocket("/ws/v2/bots/{session_id}")
async def websocket_bot_stream(
    websocket: WebSocket,
    session_id: str = Path(..., description="Bot session ID"),
    token: Optional[str] = Query(None),
):
    """
    Real-time streaming WebSocket endpoint for a specific bot session.
    Dispatches lifecycle, signal, decision, order, fill, portfolio, and health updates.
    Supports sequence IDs, heartbeats (PING/PONG), and snapshot resynchronization.
    """
    # Verify auth token if required
    auth_token = token or websocket.query_params.get("token")
    try:
        verify_api_key(token=auth_token)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(websocket, session_id=session_id)

    # Automatically dispatch initial state snapshot on connect
    snapshot = bot_api_service.get_snapshot(session_id)
    await ws_manager.send_snapshot(websocket, session_id, snapshot)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action", "").upper()

                if action == "PING":
                    # Respond with PONG heartbeat
                    await websocket.send_json({
                        "type": "PONG",
                        "timestamp": msg.get("timestamp"),
                        "server_time": datetime.now().isoformat(),
                    })
                elif action == "RESYNC":
                    last_seq_id = msg.get("last_seq_id", 0)
                    await ws_manager.resynchronize(
                        websocket=websocket,
                        session_id=session_id,
                        last_seq_id=last_seq_id,
                        fallback_snapshot_fn=bot_api_service.get_snapshot,
                    )
                elif action == "GET_SNAPSHOT":
                    snap = bot_api_service.get_snapshot(session_id)
                    await ws_manager.send_snapshot(websocket, session_id, snap)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "INVALID_JSON_PAYLOAD"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id=session_id)
    except Exception as e:
        ws_manager.disconnect(websocket, session_id=session_id)


@ws_router.websocket("/ws/v2/bots")
async def websocket_global_bot_stream(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    Global real-time streaming WebSocket endpoint receiving events from ALL bot sessions.
    """
    auth_token = token or websocket.query_params.get("token")
    try:
        verify_api_key(token=auth_token)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(websocket, session_id=None)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action", "").upper() == "PING":
                    await websocket.send_json({"type": "PONG", "server_time": datetime.now().isoformat()})
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id=None)
    except Exception:
        ws_manager.disconnect(websocket, session_id=None)
