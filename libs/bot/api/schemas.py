"""
libs/bot/api/schemas.py — Pydantic Request & Response Schemas (GĐ35)
Provides schema definitions for REST endpoints and WebSocket messages for AlgoTrading V2.0.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class RiskConfigSchema(BaseModel):
    model_config = {"extra": "forbid"}

    risk_configuration_version: str = "1.0.0"
    risk_per_trade_pct: float = Field(0.02, gt=0, le=0.50, description="Risk per trade percentage (0, 0.50]")
    max_position_notional: float = Field(25000.0, gt=0, description="Max USD position notional")
    max_position_qty: float = Field(10000.0, gt=0, description="Max units per position")
    max_symbol_exposure_pct: float = Field(0.30, gt=0, le=1.0, description="Max single symbol exposure")
    max_portfolio_exposure_pct: float = Field(1.00, gt=0, le=2.0, description="Max total portfolio exposure")
    daily_loss_limit_pct: float = Field(0.05, gt=0, le=0.50, description="Daily loss limit guard")
    max_drawdown_pct: float = Field(0.10, gt=0, le=0.50, description="Peak-to-trough drawdown lockout")
    max_concurrent_positions: int = Field(5, ge=1, le=50, description="Max concurrent open positions")
    max_price_age_seconds: int = Field(300, ge=10, le=3600, description="Stale price threshold seconds")
    allow_short: bool = False
    sizing_mode: str = Field("PERCENT_RISK", description="PERCENT_RISK, FIXED_NOTIONAL, FIXED_QTY")
    fixed_notional: float = 5000.0
    fixed_qty: float = 10.0
    environment: str = Field("SIMULATION", description="Strictly SIMULATION")


class CreateBotRequest(BaseModel):
    bot_id: str = Field("bot_v2_default", min_length=2, max_length=64, description="Unique Bot Identifier")
    bot_name: str = Field("PaperBotV2", min_length=2, max_length=64, description="Human-readable Bot Name")
    symbols: List[str] = Field(default_factory=lambda: ["NVDA", "BTC/USD"], min_length=1, description="Traded symbols")
    timeframe: str = Field("1m", description="Primary timeframe (e.g. 1m)")
    initial_cash: float = Field(100000.0, gt=0, description="Initial virtual cash balance")
    strategy_id: str = Field("MA_CROSS_1M", description="Strategy identifier")
    strategy_version: str = Field("1.0.0", description="Strategy version string")
    risk_config: Optional[RiskConfigSchema] = None
    stop_policy: str = Field("CANCEL_REMAINDER", description="CANCEL_REMAINDER or KEEP_WORKING")


class BotControlRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Reason for command action")
    policy: Optional[str] = Field(None, description="Stop policy for STOP command (CANCEL_REMAINDER or KEEP_WORKING)")


class SubmitBarRequest(BaseModel):
    symbol: str = Field(..., min_length=1, description="Ticker symbol")
    open: float = Field(..., gt=0, description="Open price")
    high: float = Field(..., gt=0, description="High price")
    low: float = Field(..., gt=0, description="Low price")
    close: float = Field(..., gt=0, description="Close price")
    volume: float = Field(..., ge=0, description="Volume")
    timeframe: str = Field("1m", description="Bar timeframe")
    event_time: Optional[datetime] = None
    is_final: bool = Field(True, description="Whether the bar is finalized")
    environment: str = Field("SIMULATION", description="Strictly SIMULATION")


class PositionSchema(BaseModel):
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    environment: str = "SIMULATION"


class BotSummaryResponse(BaseModel):
    session_id: str
    bot_id: str
    bot_name: str
    strategy_id: str
    strategy_version: str
    symbols: List[str]
    timeframe: str
    lifecycle_state: str
    status: str
    initial_cash: float
    current_equity: float
    cash: float
    available_cash: float
    reserved_cash: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    open_positions_count: int
    started_at: Optional[str] = None
    paused_at: Optional[str] = None
    stopped_at: Optional[str] = None
    last_heartbeat_at: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    risk_config_hash: str = ""
    trading_mode: str = "DRY_RUN"
    environment: str = "SIMULATION"


class PortfolioResponse(BaseModel):
    session_id: str
    portfolio_id: str
    state: str
    initial_cash: float
    cash: float
    available_cash: float
    reserved_cash: float
    equity: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    positions: List[PositionSchema]
    environment: str = "SIMULATION"


class OrderResponse(BaseModel):
    simulated_order_id: str
    bot_session_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    filled_quantity: float
    remaining_quantity: float
    average_fill_price: float
    status: str
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    submitted_at: Optional[str] = None
    filled_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    environment: str = "SIMULATION"


class FillResponse(BaseModel):
    simulated_fill_id: str
    simulated_order_id: str
    symbol: str
    side: str
    fill_price: float
    fill_qty: float
    fee: float
    slippage: float
    fill_time: str
    source_bar_key: str
    execution_bar_key: str
    environment: str = "SIMULATION"


class PerformanceResponse(BaseModel):
    session_id: str
    report_generated_at: str
    capital_metrics: Dict[str, Any]
    pnl_metrics: Dict[str, Any]
    drawdown_metrics: Dict[str, Any]
    signal_metrics: Dict[str, Any]
    order_metrics: Dict[str, Any]
    financial: Dict[str, Any]
    signals: Dict[str, Any]
    orders: Dict[str, Any]
    trades: Dict[str, Any]
    total_realized_pnl: Optional[float] = 0.0
    win_rate_pct: Optional[float] = 0.0
    total_trades: Optional[int] = 0
    signals_received: Optional[int] = 0
    signals_accepted: Optional[int] = 0
    signals_rejected: Optional[int] = 0
    max_drawdown_usd: Optional[float] = 0.0
    max_drawdown_pct: Optional[float] = 0.0
    peak_equity: Optional[float] = 0.0
    environment: str = "SIMULATION"


class HealthResponse(BaseModel):
    session_id: str
    lifecycle_state: str
    overall_status: str
    status: Optional[str] = None
    last_heartbeat_age_seconds: float = 0.0
    events_processed_count: int = 0
    event_processing_latency_ms: float = 0.0
    latency_ms: Optional[float] = 0.0
    queue_depth: int = 0
    consumer_health: str = "HEALTHY"
    strategy_engine_health: str = "HEALTHY"
    simulation_broker_health: str = "HEALTHY"
    reconciliation_status: str = "BALANCED"
    is_feed_stale: bool = False
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    error_count: int = 0
    last_error: Optional[str] = None
    environment: str = "SIMULATION"


class WebSocketMessage(BaseModel):
    seq_id: int
    session_id: str
    event_type: str
    timestamp: str
    payload: Dict[str, Any]
    environment: str = "SIMULATION"
