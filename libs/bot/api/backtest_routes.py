"""
libs/bot/api/backtest_routes.py — Backtesting REST API Endpoints (GĐ36)
Mounted at /api/v2/backtests to manage historical backtest configurations, execution,
metrics retrieval, trade inspection, equity curves, and cancellation.
Strictly isolated from natural market topics and live execution gates.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from dataclasses import asdict
import logging
import uuid
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status

from libs.alpaca_paper_gate import paper_gate, LiveTradingProhibitedError
from libs.bot.api.auth import verify_api_key
from libs.bot.backtesting.config import BacktestConfig
from libs.bot.backtesting.runner import BacktestRunner
from libs.bot.backtesting.dataset import HistoricalDatasetManager, DatasetManifest, _NY_TZ
from libs.bot.backtesting.alpaca_client import (
    AlpacaHistoricalClient,
    AlpacaHistoricalDataError,
    AlpacaAuthenticationError,
    AlpacaRateLimitExceededError,
)
from libs.bot.backtesting.store import BacktestStore
from libs.bot.backtesting.trade_ledger import (
    serialize_candles,
    compute_strategy_indicators,
    build_closed_trades_and_associations,
)
from libs.bot.domain import MarketDataEvent
from libs.bot.api.historical_routes import dataset_manager

logger = logging.getLogger("backtest-api")

router = APIRouter(prefix="/api/v2/backtests", tags=["V2 Backtesting Engine"])

# Global singleton stores & runner registry
backtest_store = BacktestStore()
_active_runners: Dict[str, BacktestRunner] = {}


# --- Request & Response Models ---

class CreateBacktestRequest(BaseModel):
    strategy_id: str = Field(default="MA_CROSS_1M", description="Strategy identifier")
    strategy_version: str = Field(default="1.0.0", description="Strategy version string")
    symbols: List[str] = Field(default=["NVDA"], description="List of symbols to backtest")
    asset_classes: Optional[Dict[str, str]] = Field(default=None, description="Mapping of symbol to STOCKS or CRYPTO")
    timeframe: str = Field(default="1m", description="Primary bar timeframe")
    start_time: Optional[datetime] = Field(default=None, description="Backtest start timestamp")
    end_time: Optional[datetime] = Field(default=None, description="Backtest end timestamp")
    initial_simulated_cash: float = Field(default=100000.0, ge=100.0, description="Virtual starting equity in USD")
    fee_model: str = Field(default="DEFAULT", description="ZERO, DEFAULT, or CONFIGURABLE")
    slippage_model: str = Field(default="DEFAULT", description="ZERO, DEFAULT, or IMPACT")
    volume_participation_rate: float = Field(default=0.10, gt=0.0, le=1.0, description="Max bar volume fill ratio")
    market_session_policy: str = Field(default="STRICT_HOURS", description="STRICT_HOURS or ALL_HOURS")
    warmup_bars_count: int = Field(default=50, ge=0, description="Number of bars for indicator warmup without trading")
    seed: Optional[int] = Field(default=42, description="Random seed for deterministic replay")
    execution_config: Optional[Dict[str, Any]] = Field(default=None, description="Strategy parameters and fee settings")
    dataset_id: Optional[str] = Field(default=None, description="Existing historical dataset ID to replay")
    synthetic_bars_count: Optional[int] = Field(default=None, ge=10, description="Generate synthetic bars if no dataset is specified")


# Helper to generate synthetic test bars when requested
def _generate_synthetic_bars(symbols: List[str], count: int, asset_class: str = "STOCKS") -> List[MarketDataEvent]:
    base_time = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
    bars = []
    for sym in symbols:
        price = 150.0 if sym != "BTC/USD" else 60000.0
        for i in range(count):
            t = base_time + timedelta(minutes=i)
            delta = 0.8 if i % 2 == 0 else -0.4
            price += delta
            bar = MarketDataEvent(
                event_id=f"syn_{sym}_{i}",
                event_time=t,
                ingest_time=t,
                symbol=sym,
                asset_class=asset_class,
                timeframe="1m",
                open=Decimal(str(round(price - 0.2, 4))),
                high=Decimal(str(round(price + 0.5, 4))),
                low=Decimal(str(round(price - 0.5, 4))),
                close=Decimal(str(round(price, 4))),
                volume=Decimal("2000"),
                is_final=True,
                environment="SIMULATION",
            )
            bars.append(bar)
    return bars


# --- Endpoints ---

@router.post("", status_code=status.HTTP_201_CREATED, summary="Create and execute a backtest run")
def create_backtest(
    req: CreateBacktestRequest,
    authorized: bool = Depends(verify_api_key),
):
    """
    Launches an isolated quantitative strategy backtest using AlgoTrading V2.0 simulation components.
    Guarantees:
    - Strictly environment='SIMULATION'
    - Closed PaperExecutionGate
    - Deterministic replay
    """
    if paper_gate.is_gate_open:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="LiveTradingProhibitedError: PaperExecutionGate is OPEN. Backtest aborted.",
        )

    run_id = f"bt_{uuid.uuid4().hex[:12]}"
    asset_cls_map = req.asset_classes or {s: ("CRYPTO" if "/" in s else "STOCKS") for s in req.symbols}

    cfg = BacktestConfig(
        backtest_run_id=run_id,
        strategy_id=req.strategy_id,
        strategy_version=req.strategy_version,
        symbols=req.symbols,
        asset_classes=asset_cls_map,
        timeframe=req.timeframe,
        start_time=req.start_time,
        end_time=req.end_time,
        initial_simulated_cash=req.initial_simulated_cash,
        fee_model=req.fee_model,
        slippage_model=req.slippage_model,
        volume_participation_rate=req.volume_participation_rate,
        market_session_policy=req.market_session_policy,
        warmup_bars_count=req.warmup_bars_count,
        seed=req.seed,
        execution_config=req.execution_config or {},
        environment="SIMULATION",
    )

    runner = BacktestRunner(
        config=cfg,
        dataset_manager=dataset_manager,
        store=backtest_store,
    )
    _active_runners[run_id] = runner

    # Resolve dataset or synthetic bars
    bars: Optional[List[MarketDataEvent]] = None
    manifest: Optional[DatasetManifest] = None
    if req.dataset_id:
        try:
            bars = dataset_manager.load_dataset(req.dataset_id)
            manifest = dataset_manager.get_manifest(req.dataset_id)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset error: {e}")
    else:
        bar_count = req.synthetic_bars_count or 120
        primary_ac = asset_cls_map.get(req.symbols[0], "STOCKS")
        syn_bars = _generate_synthetic_bars(req.symbols, count=bar_count, asset_class=primary_ac)
        bars, manifest = dataset_manager.create_dataset_from_bars(
            dataset_id=f"syn_ds_{run_id}",
            bars=syn_bars,
            is_synthetic=True,
            asset_classes=asset_cls_map,
            provider="SYNTHETIC_GENERATOR",
            source_type="SYNTHETIC_FIXTURE",
            feed="SYNTHETIC",
        )

    try:
        result = runner.run(bars, dataset_manifest=manifest)
        return {
            "status": "COMPLETED",
            "run_id": result.run_id,
            "strategy_id": result.config.strategy_id,
            "symbols": result.config.symbols,
            "metrics": result.metrics,
            "deterministic_fingerprint": result.compute_deterministic_fingerprint(),
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "environment": result.environment,
        }
    except Exception as e:
        logger.error(f"Backtest run failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest execution failed: {str(e)}",
        )
    finally:
        _active_runners.pop(run_id, None)


@router.get("", summary="List all historical backtest runs")
def list_backtests(
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves all stored backtest runs."""
    return backtest_store.list_runs()


@router.get("/{run_id}", summary="Get backtest summary by run_id")
def get_backtest(
    run_id: str = Path(..., description="Backtest run ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves metadata and summary metrics for a specific backtest run."""
    res = backtest_store.get_result(run_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Backtest run '{run_id}' not found")
    return res


@router.get("/{run_id}/results", summary="Get complete backtest results and metrics")
def get_backtest_results(
    run_id: str = Path(..., description="Backtest run ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves full quantitative performance report and execution metrics."""
    res = backtest_store.get_result(run_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Backtest run '{run_id}' not found")
    manifest = res.get("dataset") or res.get("manifest") or backtest_store.get_manifest(run_id)
    is_synth = manifest.get("is_synthetic", False) if isinstance(manifest, dict) else False
    return {
        "run_id": run_id,
        "config": res.get("config"),
        "metrics": res.get("metrics"),
        "deterministic_fingerprint": res.get("deterministic_fingerprint"),
        "orders_count": res.get("orders_count", 0),
        "fills_count": res.get("fills_count", 0),
        "closed_trades_count": res.get("closed_trades_count", 0),
        "positions": res.get("positions", []),
        "dataset": manifest,
        "data_source": res.get("data_source") or ("SYNTHETIC_FIXTURE" if is_synth else "LOCAL_CACHE" if manifest else "SYNTHETIC"),
        "started_at": res.get("started_at"),
        "completed_at": res.get("completed_at"),
    }


@router.get("/{run_id}/trades", summary="Get backtest trades and fills")
def get_backtest_trades(
    run_id: str = Path(..., description="Backtest run ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves all simulated fills and round-trip trades."""
    res = backtest_store.get_result(run_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Backtest run '{run_id}' not found")
    return backtest_store.get_trades(run_id)


@router.get("/{run_id}/equity", summary="Get equity curve time series")
def get_backtest_equity(
    run_id: str = Path(..., description="Backtest run ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves sequential equity curve data points."""
    res = backtest_store.get_result(run_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Backtest run '{run_id}' not found")
    return backtest_store.get_equity_curve(run_id)


def _enrich_chart_diagnostics(
    candles: List[Dict[str, Any]],
    gaps: List[Dict[str, Any]],
    indicators: Dict[str, Any],
    cfg: Dict[str, Any],
    manifest: Any,
) -> Dict[str, Any]:
    """Enriches serialized candles/gaps with session tags, gap summaries, and requested-vs-actual windows."""
    asset_classes = cfg.get("asset_classes") or {}
    session_counts: Dict[str, int] = {}

    for c in candles:
        sym = c.get("symbol", "")
        inferred_ac = "CRYPTO" if "/" in sym else "STOCKS"
        ac = asset_classes.get(sym, inferred_ac)
        if not c.get("session") or not c.get("ny_time"):
            dt = datetime.fromisoformat(str(c["timestamp"])) if c.get("timestamp") else datetime.fromtimestamp(c["time"], tz=timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_utc = dt.astimezone(timezone.utc)
            c.setdefault("session", HistoricalDatasetManager.classify_market_session(dt_utc, ac))
            c.setdefault("ny_time", dt_utc.astimezone(_NY_TZ).strftime("%Y-%m-%d %H:%M"))
        sess = c["session"]
        session_counts[sess] = session_counts.get(sess, 0) + 1

    for g in gaps:
        if not g.get("gap_type"):
            sym = g.get("symbol", "")
            ac = asset_classes.get(sym, "CRYPTO" if "/" in sym else "STOCKS")
            cur_dt = datetime.fromisoformat(str(g["gap_start"]))
            nxt_dt = datetime.fromisoformat(str(g["gap_end"]))
            if cur_dt.tzinfo is None:
                cur_dt = cur_dt.replace(tzinfo=timezone.utc)
            if nxt_dt.tzinfo is None:
                nxt_dt = nxt_dt.replace(tzinfo=timezone.utc)
            diff_sec = float(g.get("gap_duration_seconds") or g.get("gap_seconds") or (nxt_dt - cur_dt).total_seconds())
            gtype, sctx = HistoricalDatasetManager._classify_gap(
                cur_dt.astimezone(timezone.utc), nxt_dt.astimezone(timezone.utc), ac, diff_sec
            )
            g["gap_type"] = gtype
            g["session_context"] = sctx

    readiness_by_symbol = dict(indicators.get("readiness_by_symbol") or {})
    if not readiness_by_symbol and isinstance(indicators.get("series_by_symbol"), dict):
        for sym, series_dict in indicators["series_by_symbol"].items():
            total_pts = max(len(series_dict.get("ma_fast", [])), len(series_dict.get("ma_slow", [])), len(series_dict.get("rsi", [])))
            r_entry: Dict[str, Any] = {"total_bars": total_pts}
            for key, prefix in (("ma_fast", "ma_fast"), ("ma_slow", "ma_slow"), ("rsi", "rsi")):
                pts = series_dict.get(key, [])
                ready_idx = next((idx + 1 for idx, pt in enumerate(pts) if pt.get("warmup_complete")), None)
                r_entry[f"{prefix}_ready_bar"] = ready_idx
                r_entry[f"{prefix}_ready_time"] = pts[ready_idx - 1].get("timestamp") if ready_idx else None
            readiness_by_symbol[sym] = r_entry

    manifest_dict = manifest if isinstance(manifest, dict) else {}
    requested_window = {
        "start": cfg.get("start_time") or manifest_dict.get("requested_start") or manifest_dict.get("start_time"),
        "end": cfg.get("end_time") or manifest_dict.get("requested_end") or manifest_dict.get("end_time"),
        "session_policy": cfg.get("market_session_policy", "STRICT_HOURS"),
        "source_dataset_id": manifest_dict.get("dataset_id"),
    }
    actual_window = {
        "first_bar": candles[0]["timestamp"] if candles else manifest_dict.get("start_time"),
        "last_bar": candles[-1]["timestamp"] if candles else manifest_dict.get("end_time"),
        "candles_count": len(candles),
        "manifest_total_bars": manifest_dict.get("total_bars"),
        "warmup_bars_count": int(cfg.get("warmup_bars_count", 0)),
    }
    gap_summary = HistoricalDatasetManager.summarize_gaps(gaps)
    warnings: List[str] = []
    strat_id = str(cfg.get("strategy_id", "MA_CROSS_1M")).upper()
    ind_params = indicators.get("params") or {}
    req_ind_bars = int(ind_params.get("rsi_period", 14)) if "RSI" in strat_id else int(ind_params.get("slow_period", 50))
    if len(candles) < req_ind_bars:
        warnings.append(
            f"Dataset has {len(candles)} bars which is fewer than {strat_id} indicator warmup requirement ({req_ind_bars})."
        )
    if gap_summary.get("rth_missing", 0) > 0:
        warnings.append(
            f"{gap_summary['rth_missing']} regular-hours 1m interval(s) have no trade prints in source feed (kept uninterpolated)."
        )
    if gap_summary.get("feed_gap", 0) > 0:
        warnings.append(
            f"{gap_summary['feed_gap']} crypto 24/7 interval(s) missing in source feed (kept uninterpolated)."
        )

    return {
        "session_counts": session_counts,
        "gap_summary": gap_summary,
        "indicator_readiness": readiness_by_symbol,
        "requested_window": requested_window,
        "actual_window": actual_window,
        "data_quality_warnings": warnings,
    }


@router.get("/{run_id}/chart", summary="Get complete interactive trade chart bundle (GĐ41)")
def get_backtest_chart(
    run_id: str = Path(..., description="Backtest run ID"),
    authorized: bool = Depends(verify_api_key),
):
    """
    Returns synchronized OHLCV bars, Strategy Engine indicators (MA Fast/Slow, RSI 14),
    StrategySignal events, SimulatedOrder/SimulatedFill execution ledger, portfolio transactions,
    matched closed trades, gaps, and dataset provenance for interactive TradingView visualization.
    Never recomputes trades client-side or replaces fill prices with bar closes.
    """
    res = backtest_store.get_result(run_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Backtest run '{run_id}' not found")

    cfg = res.get("config") or {}
    manifest = res.get("dataset") or res.get("manifest") or backtest_store.get_manifest(run_id)
    candles = backtest_store.get_bars(run_id)
    indicators = backtest_store.get_indicators(run_id)
    signals = backtest_store.get_signals(run_id)
    decisions = backtest_store.get_decisions(run_id)
    orders = backtest_store.get_orders(run_id)
    fills = backtest_store.get_trades(run_id)
    transactions = backtest_store.get_transactions(run_id)
    closed_trades = backtest_store.get_closed_trades(run_id)
    gaps = backtest_store.get_gaps(run_id)
    equity_curve = backtest_store.get_equity_curve(run_id)

    # Graceful reconstruction for legacy runs without persisted bars.json / indicators.json
    if not candles:
        ds_id = (manifest.get("dataset_id") if isinstance(manifest, dict) else None) or f"auto_ds_{run_id}"
        raw_bars = dataset_manager.load_dataset(ds_id) or dataset_manager.load_dataset(f"auto_ds_{run_id}")
        if raw_bars:
            if not manifest:
                m_obj = dataset_manager.get_manifest(ds_id) or dataset_manager.get_manifest(f"auto_ds_{run_id}")
                if m_obj:
                    manifest = m_obj.to_dict()
            warmup_cnt = int(cfg.get("warmup_bars_count", 0))
            if len(raw_bars) < warmup_cnt and cfg.get("warmup_policy", "AUTO") != "REQUIRED":
                warmup_cnt = min(warmup_cnt, len(raw_bars) // 2)
            candles = serialize_candles(raw_bars, warmup_count=warmup_cnt, asset_classes=cfg.get("asset_classes"))
            indicators = compute_strategy_indicators(
                bars=raw_bars,
                strategy_id=cfg.get("strategy_id", "MA_CROSS_1M"),
                execution_config=cfg.get("execution_config"),
            )
            gaps = dataset_manager.detect_gaps(raw_bars, asset_classes=cfg.get("asset_classes"))

    if not closed_trades and fills:
        sig_map = {s["signal_id"]: s for s in signals if "signal_id" in s}
        closed_trades = build_closed_trades_and_associations(fills=fills, signals_by_id=sig_map)

    diag = _enrich_chart_diagnostics(candles=candles, gaps=gaps, indicators=indicators, cfg=cfg, manifest=manifest)

    is_synth = manifest.get("is_synthetic", False) if isinstance(manifest, dict) else True
    data_source = "SYNTHETIC_FIXTURE" if is_synth else (
        "ALPACA_MARKET_DATA_API" if (isinstance(manifest, dict) and manifest.get("provider") == "ALPACA") else "LOCAL_CACHE"
    )

    return {
        "run_id": run_id,
        "config": cfg,
        "dataset_manifest": manifest,
        "data_source": data_source,
        "environment": res.get("environment", "SIMULATION"),
        "trading_mode": "DRY_RUN",
        "paper_execution_gate": "CLOSED",
        "symbols": cfg.get("symbols", []),
        "timeframe": cfg.get("timeframe", "1m"),
        "warmup_bars_count": int(cfg.get("warmup_bars_count", 0)),
        "session_policy": cfg.get("market_session_policy", "STRICT_HOURS"),
        "session_counts": diag["session_counts"],
        "gap_summary": diag["gap_summary"],
        "indicator_readiness": diag["indicator_readiness"],
        "requested_window": diag["requested_window"],
        "actual_window": diag["actual_window"],
        "data_quality_warnings": diag["data_quality_warnings"],
        "candles": candles,
        "indicators": indicators,
        "signals": signals,
        "decisions": decisions,
        "orders": orders,
        "fills": fills,
        "portfolio_transactions": transactions,
        "closed_trades": closed_trades,
        "gaps": gaps,
        "equity_curve": equity_curve,
        "metrics": res.get("metrics"),
        "deterministic_fingerprint": res.get("deterministic_fingerprint"),
    }


@router.post("/{run_id}/cancel", summary="Cancel an active backtest run")
def cancel_backtest(
    run_id: str = Path(..., description="Backtest run ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Cancels a running backtest."""
    if run_id in _active_runners:
        runner = _active_runners[run_id]
        if runner.controller:
            runner.controller.cancel()
        _active_runners.pop(run_id, None)
        return {"run_id": run_id, "status": "CANCELLED"}

    res = backtest_store.get_result(run_id)
    if res:
        return {"run_id": run_id, "status": "ALREADY_COMPLETED"}

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Backtest run '{run_id}' not found")


@router.delete("/{run_id}", summary="Delete backtest run artifacts")
def delete_backtest(
    run_id: str = Path(..., description="Backtest run ID"),
    authorized: bool = Depends(verify_api_key),
):
    """Removes stored artifacts for a backtest run."""
    deleted = backtest_store.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Backtest run '{run_id}' not found")
    return {"run_id": run_id, "status": "DELETED"}


# --- GĐ41: One-Click Alpaca Historical Fetch & Backtest ---

class OneClickAlpacaBacktestRequest(BaseModel):
    symbol: str = Field(default="NVDA", description="Symbol to fetch and backtest (e.g. NVDA, AAPL, BTC/USD)")
    asset_class: Optional[str] = Field(default=None, description="STOCKS or CRYPTO (auto-detected if None)")
    timeframe: str = Field(default="1m", description="Bar timeframe: 1m")
    start_time: datetime = Field(..., description="Start of historical window (UTC)")
    end_time: datetime = Field(..., description="End of historical window (UTC)")
    feed: str = Field(default="IEX", description="Stock data feed: IEX or SIP")
    force_refresh: bool = Field(default=False, description="Bypass cache and force fresh Alpaca fetch")
    strategy_id: str = Field(default="MA_CROSS_1M", description="Strategy identifier")
    strategy_version: str = Field(default="1.0.0", description="Strategy version string")
    initial_simulated_cash: float = Field(default=100000.0, ge=100.0, description="Virtual starting equity in USD")
    fee_model: str = Field(default="DEFAULT", description="ZERO, DEFAULT, or CONFIGURABLE")
    slippage_model: str = Field(default="DEFAULT", description="ZERO, DEFAULT, or IMPACT")
    volume_participation_rate: float = Field(default=0.10, gt=0.0, le=1.0, description="Max bar volume fill ratio")
    market_session_policy: str = Field(default="STRICT_HOURS", description="STRICT_HOURS or ALL_HOURS")
    warmup_bars_count: int = Field(default=20, ge=0, description="Indicator warmup bar count")
    seed: Optional[int] = Field(default=42, description="Deterministic replay seed")
    execution_config: Optional[Dict[str, Any]] = Field(default=None, description="Execution and fee overrides")


class FromDatasetBacktestRequest(BaseModel):
    dataset_id: str = Field(..., description="ID of existing dataset in cache or manifest")
    strategy_id: str = Field(default="MA_CROSS_1M", description="Strategy identifier")
    strategy_version: str = Field(default="1.0.0", description="Strategy version string")
    initial_simulated_cash: float = Field(default=100000.0, ge=100.0, description="Virtual starting equity in USD")
    fee_model: str = Field(default="DEFAULT", description="ZERO, DEFAULT, or CONFIGURABLE")
    slippage_model: str = Field(default="DEFAULT", description="ZERO, DEFAULT, or IMPACT")
    volume_participation_rate: float = Field(default=0.10, gt=0.0, le=1.0)
    market_session_policy: str = Field(default="STRICT_HOURS", description="STRICT_HOURS or ALL_HOURS")
    warmup_bars_count: int = Field(default=20, ge=0)
    seed: Optional[int] = Field(default=42)
    execution_config: Optional[Dict[str, Any]] = Field(default=None)


@router.post("/from-alpaca", status_code=status.HTTP_201_CREATED, summary="One-click Fetch from Alpaca & Backtest (GĐ41)")
def backtest_from_alpaca(
    req: OneClickAlpacaBacktestRequest,
    authorized: bool = Depends(verify_api_key),
):
    """
    Executes a quantitative backtest directly from real Alpaca historical data.
    Flow:
    1. Check local cache (unless force_refresh=True)
    2. If not cached, fetch 1m OHLCV bars from Alpaca Market Data API
    3. Validate OHLCV mathematical invariants
    4. Snapshot immutable dataset manifest with SHA-256
    5. Run next-eligible-bar deterministic backtest
    6. Return full metrics, provenance, trades, and deterministic fingerprint
    """
    if paper_gate.is_gate_open:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="LiveTradingProhibitedError: PaperExecutionGate is OPEN.",
        )

    sym_clean = AlpacaHistoricalClient.normalize_symbol(req.symbol)
    asset_class = req.asset_class or AlpacaHistoricalClient.detect_asset_class(sym_clean)
    feed_clean = "CRYPTO" if asset_class == "CRYPTO" else req.feed.upper()

    bars: Optional[List[MarketDataEvent]] = None
    manifest: Optional[DatasetManifest] = None
    data_source: str = "ALPACA_MARKET_DATA_API"

    # 1. Cache lookup
    if not req.force_refresh:
        cached_manifest = dataset_manager.find_cached_dataset(
            symbol=sym_clean,
            timeframe=req.timeframe,
            feed=feed_clean,
            start_time=req.start_time,
            end_time=req.end_time,
        )
        if cached_manifest:
            loaded = dataset_manager.load_dataset(cached_manifest.dataset_id)
            if loaded:
                bars = loaded
                manifest = cached_manifest
                data_source = "LOCAL_CACHE"

    # 2. Live fetch if not in cache
    if bars is None:
        try:
            client = AlpacaHistoricalClient()
            fetched_bars, fetch_meta = client.fetch_bars(
                symbol=sym_clean,
                start_time=req.start_time,
                end_time=req.end_time,
                timeframe=req.timeframe,
                feed=feed_clean,
            )
        except AlpacaAuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Alpaca authentication failed: {exc}",
            )
        except AlpacaRateLimitExceededError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Alpaca rate limit exceeded (HTTP 429): {exc}",
            )
        except AlpacaHistoricalDataError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Alpaca historical data fetch failed: {exc}",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error while fetching historical data: {exc}",
            )

        if not fetched_bars:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Alpaca returned 0 bars for {sym_clean} in window [{req.start_time.isoformat()}, {req.end_time.isoformat()}]. "
                    f"Ensure dates are in the past and within regular trading hours (Mon-Fri 14:30-21:00 UTC for equities)."
                ),
            )

        clean_sym_tag = sym_clean.replace('/', '_').replace('-', '_')
        dataset_id = f"ds_alpaca_{clean_sym_tag}_{uuid.uuid4().hex[:8]}"

        sanitized, ds_manifest = dataset_manager.create_dataset_from_bars(
            dataset_id=dataset_id,
            bars=fetched_bars,
            version="1.0.0",
            is_synthetic=False,
            provider="ALPACA",
            source_type="REAL_HISTORICAL_MARKET_DATA",
            feed=feed_clean,
            asset_class=asset_class,
            requested_start=req.start_time.isoformat(),
            requested_end=req.end_time.isoformat(),
            source_api_metadata=fetch_meta,
            persist_to_disk=True,
        )
        bars = sanitized
        manifest = ds_manifest
        data_source = "ALPACA_MARKET_DATA_API"

    run_id = f"bt_alpaca_{uuid.uuid4().hex[:12]}"
    cfg = BacktestConfig(
        backtest_run_id=run_id,
        strategy_id=req.strategy_id,
        strategy_version=req.strategy_version,
        symbols=[sym_clean],
        asset_classes={sym_clean: asset_class},
        timeframe=req.timeframe,
        start_time=req.start_time,
        end_time=req.end_time,
        initial_simulated_cash=req.initial_simulated_cash,
        fee_model=req.fee_model,
        slippage_model=req.slippage_model,
        volume_participation_rate=req.volume_participation_rate,
        market_session_policy=req.market_session_policy,
        warmup_bars_count=req.warmup_bars_count,
        seed=req.seed,
        execution_config=req.execution_config or {},
        environment="SIMULATION",
    )

    runner = BacktestRunner(
        config=cfg,
        dataset_manager=dataset_manager,
        store=backtest_store,
    )
    _active_runners[run_id] = runner

    try:
        result = runner.run(bars, dataset_manifest=manifest)
        return {
            "status": "COMPLETED",
            "run_id": result.run_id,
            "strategy_id": result.config.strategy_id,
            "symbols": result.config.symbols,
            "metrics": result.metrics,
            "deterministic_fingerprint": result.compute_deterministic_fingerprint(),
            "dataset": manifest.to_dict() if manifest else None,
            "data_source": data_source,
            "orders_count": len(result.orders),
            "fills_count": len(result.fills),
            "equity_points_count": len(result.equity_curve),
            "positions": result.positions,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "environment": result.environment,
            "trading_mode": "DRY_RUN",
            "paper_execution_gate": "CLOSED",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Alpaca backtest run failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest execution failed: {str(e)}",
        )
    finally:
        _active_runners.pop(run_id, None)


@router.post("/from-dataset", status_code=status.HTTP_201_CREATED, summary="Backtest from an existing historical dataset (GĐ41)")
def backtest_from_dataset(
    req: FromDatasetBacktestRequest,
    authorized: bool = Depends(verify_api_key),
):
    """Executes a backtest using an existing cached or uploaded dataset ID."""
    if paper_gate.is_gate_open:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="LiveTradingProhibitedError: PaperExecutionGate is OPEN.",
        )

    bars = dataset_manager.load_dataset(req.dataset_id)
    if not bars:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{req.dataset_id}' not found")

    manifest = dataset_manager.get_manifest(req.dataset_id)
    run_id = f"bt_ds_{uuid.uuid4().hex[:12]}"
    symbols = list(set(b.symbol for b in bars))
    asset_cls_map = {s: ("CRYPTO" if "/" in s else "STOCKS") for s in symbols}

    cfg = BacktestConfig(
        backtest_run_id=run_id,
        strategy_id=req.strategy_id,
        strategy_version=req.strategy_version,
        symbols=symbols,
        asset_classes=asset_cls_map,
        timeframe=bars[0].timeframe,
        initial_simulated_cash=req.initial_simulated_cash,
        fee_model=req.fee_model,
        slippage_model=req.slippage_model,
        volume_participation_rate=req.volume_participation_rate,
        market_session_policy=req.market_session_policy,
        warmup_bars_count=req.warmup_bars_count,
        seed=req.seed,
        execution_config=req.execution_config or {},
        environment="SIMULATION",
    )

    runner = BacktestRunner(
        config=cfg,
        dataset_manager=dataset_manager,
        store=backtest_store,
    )
    _active_runners[run_id] = runner

    try:
        result = runner.run(bars, dataset_manifest=manifest)
        return {
            "status": "COMPLETED",
            "run_id": result.run_id,
            "strategy_id": result.config.strategy_id,
            "symbols": result.config.symbols,
            "metrics": result.metrics,
            "deterministic_fingerprint": result.compute_deterministic_fingerprint(),
            "dataset": manifest.to_dict() if manifest else None,
            "data_source": "LOCAL_CACHE",
            "orders_count": len(result.orders),
            "fills_count": len(result.fills),
            "equity_points_count": len(result.equity_curve),
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "environment": result.environment,
            "trading_mode": "DRY_RUN",
            "paper_execution_gate": "CLOSED",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Dataset backtest failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest execution failed: {str(e)}",
        )
    finally:
        _active_runners.pop(run_id, None)
