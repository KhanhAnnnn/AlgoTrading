"""
libs/bot/api — V2 Paper Trading Bot REST & WebSocket API Package (GĐ35)
Provides FastAPI endpoints, schemas, service layer, and real-time WebSocket protocol.
"""

from libs.bot.api.schemas import (
    RiskConfigSchema,
    CreateBotRequest,
    BotControlRequest,
    SubmitBarRequest,
    BotSummaryResponse,
    PortfolioResponse,
    OrderResponse,
    FillResponse,
    PerformanceResponse,
    HealthResponse,
    WebSocketMessage,
)
from libs.bot.api.service import BotApiService, bot_api_service
from libs.bot.api.websocket import BotWebSocketManager, ws_manager
from libs.bot.api.routes import router as v2_bots_router, ws_router as v2_ws_router
from libs.bot.api.backtest_routes import router as v2_backtests_router
from libs.bot.api.experiment_routes import router as v2_experiments_router
from libs.bot.api.historical_routes import router as v2_historical_router
from libs.bot.api.auth import verify_api_key

__all__ = [
    "RiskConfigSchema",
    "CreateBotRequest",
    "BotControlRequest",
    "SubmitBarRequest",
    "BotSummaryResponse",
    "PortfolioResponse",
    "OrderResponse",
    "FillResponse",
    "PerformanceResponse",
    "HealthResponse",
    "WebSocketMessage",
    "BotApiService",
    "bot_api_service",
    "BotWebSocketManager",
    "ws_manager",
    "v2_bots_router",
    "v2_ws_router",
    "v2_backtests_router",
    "v2_experiments_router",
    "v2_historical_router",
    "verify_api_key",
]
