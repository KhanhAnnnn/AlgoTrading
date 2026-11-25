"""
libs/bot/api/historical_routes.py — Historical Market Data Management API (GĐ41)
Mounted at /api/v2/historical-data to manage Alpaca historical fetches, dataset caching,
provenance auditing, and CSV exports.
Strictly read-only with respect to external brokers; PaperExecutionGate remains closed.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging
import uuid
import os
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from fastapi.responses import FileResponse, PlainTextResponse

from libs.alpaca_paper_gate import paper_gate
from libs.bot.api.auth import verify_api_key
from libs.bot.backtesting.dataset import HistoricalDatasetManager, DatasetManifest
from libs.bot.backtesting.alpaca_client import (
    AlpacaHistoricalClient,
    AlpacaHistoricalDataError,
    AlpacaAuthenticationError,
    AlpacaRateLimitExceededError,
)

logger = logging.getLogger("historical-data-api")

router = APIRouter(prefix="/api/v2/historical-data", tags=["V2 Historical Market Data"])

# Shared dataset manager instance
dataset_manager = HistoricalDatasetManager()


class FetchHistoricalDataRequest(BaseModel):
    symbol: str = Field(default="NVDA", description="Symbol to fetch (e.g. NVDA, AAPL, BTC/USD, ETH/USD)")
    asset_class: Optional[str] = Field(default=None, description="STOCKS or CRYPTO (auto-detected if None)")
    timeframe: str = Field(default="1m", description="Bar timeframe: 1m, 5m")
    start_time: datetime = Field(..., description="Start of historical window (UTC)")
    end_time: datetime = Field(..., description="End of historical window (UTC)")
    feed: str = Field(default="IEX", description="Stock feed: IEX or SIP")
    force_refresh: bool = Field(default=False, description="If True, ignores existing local cache and refetches")
    dataset_name: Optional[str] = Field(default=None, description="Optional custom dataset name or ID")


@router.get("/symbols", summary="List supported Stocks and Crypto symbols (GĐ41)")
def list_supported_symbols(
    authorized: bool = Depends(verify_api_key),
):
    """Returns authoritative Stocks & Crypto symbol registry and supported timeframes."""
    return AlpacaHistoricalClient.get_supported_assets()


@router.post("/fetch", status_code=status.HTTP_200_OK, summary="Fetch historical market data from Alpaca")
def fetch_historical_data(
    req: FetchHistoricalDataRequest,
    authorized: bool = Depends(verify_api_key),
):
    """
    Fetches 1-minute OHLCV historical market data from Alpaca (Stocks or Crypto),
    validates OHLCV integrity, creates an immutable dataset manifest with SHA-256 checksum,
    and caches the dataset locally for instant reuse.
    Never returns synthetic data or falls back silently.
    """
    if paper_gate.is_gate_open:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="LiveTradingProhibitedError: PaperExecutionGate is OPEN.",
        )

    sym_clean = AlpacaHistoricalClient.normalize_symbol(req.symbol)
    asset_class = req.asset_class or AlpacaHistoricalClient.detect_asset_class(sym_clean)
    feed_clean = "CRYPTO" if asset_class == "CRYPTO" else req.feed.upper()

    # 1. Check local cache if not forcing refresh
    if not req.force_refresh:
        cached_manifest = dataset_manager.find_cached_dataset(
            symbol=sym_clean,
            timeframe=req.timeframe,
            feed=feed_clean,
            start_time=req.start_time,
            end_time=req.end_time,
        )
        if cached_manifest:
            logger.info(f"Returning cached dataset '{cached_manifest.dataset_id}' for {sym_clean}")
            return {
                "status": "CACHED",
                "message": f"Using verified local cache dataset '{cached_manifest.dataset_id}'",
                "dataset_id": cached_manifest.dataset_id,
                "manifest": cached_manifest.to_dict(),
                "bars_count": cached_manifest.total_bars,
                "checksum_sha256": cached_manifest.checksum_sha256,
                "source": "LOCAL_CACHE",
            }

    # 2. Fetch fresh from Alpaca
    try:
        client = AlpacaHistoricalClient()
        bars, fetch_meta = client.fetch_bars(
            symbol=sym_clean,
            start_time=req.start_time,
            end_time=req.end_time,
            timeframe=req.timeframe,
            feed=feed_clean,
        )
    except AlpacaAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Alpaca authentication failed: {exc}. Verify APCA_API_KEY_ID and APCA_API_SECRET_KEY.",
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

    if not bars:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Alpaca returned 0 bars for {sym_clean} in window [{req.start_time.isoformat()}, {req.end_time.isoformat()}]. "
                f"Check that timestamps correspond to past trading hours (for equities: Mon-Fri 14:30-21:00 UTC)."
            ),
        )

    # 3. Create immutable dataset snapshot
    clean_sym_tag = sym_clean.replace('/', '_').replace('-', '_')
    dataset_id = req.dataset_name or f"ds_alpaca_{clean_sym_tag}_{uuid.uuid4().hex[:8]}"

    sanitized, manifest = dataset_manager.create_dataset_from_bars(
        dataset_id=dataset_id,
        bars=bars,
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

    return {
        "status": "FETCHED",
        "message": f"Successfully fetched {len(sanitized)} real bars from Alpaca and cached dataset '{dataset_id}'",
        "dataset_id": dataset_id,
        "manifest": manifest.to_dict(),
        "bars_count": manifest.total_bars,
        "checksum_sha256": manifest.checksum_sha256,
        "source": "ALPACA_MARKET_DATA_API",
    }


@router.get("/datasets", summary="List all historical datasets")
def list_datasets(
    authorized: bool = Depends(verify_api_key),
):
    """Lists all available historical datasets in memory and on disk."""
    manifests = dataset_manager.list_manifests()
    return [m.to_dict() for m in manifests]


@router.get("/datasets/{dataset_id}", summary="Get dataset manifest by ID")
def get_dataset(
    dataset_id: str = Path(..., description="Dataset identifier"),
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves metadata, checksum, and provenance for a specific dataset."""
    manifest = dataset_manager.get_manifest(dataset_id)
    if not manifest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found")
    return manifest.to_dict()


@router.get("/datasets/{dataset_id}/bars", summary="Get sample or paginated bars from dataset")
def get_dataset_bars(
    dataset_id: str = Path(..., description="Dataset identifier"),
    limit: int = Query(100, ge=1, le=1000, description="Max bars to return"),
    offset: int = Query(0, ge=0, description="Bar offset"),
    authorized: bool = Depends(verify_api_key),
):
    """Retrieves bar records for inspection from a dataset."""
    bars = dataset_manager.load_dataset(dataset_id)
    if bars is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found")

    slice_bars = bars[offset : offset + limit]
    return {
        "dataset_id": dataset_id,
        "total_bars": len(bars),
        "limit": limit,
        "offset": offset,
        "bars": [
            {
                "event_time": b.event_time.isoformat(),
                "symbol": b.symbol,
                "asset_class": b.asset_class,
                "timeframe": b.timeframe,
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
                "trade_count": getattr(b, "trade_count", 0),
                "vwap": float(getattr(b, "vwap", 0.0)),
                "provenance": b.provenance,
            }
            for b in slice_bars
        ],
    }


@router.get("/datasets/{dataset_id}/csv", summary="Export dataset to CSV")
def export_dataset_csv(
    dataset_id: str = Path(..., description="Dataset identifier"),
    authorized: bool = Depends(verify_api_key),
):
    """Exports dataset to a downloadable CSV file."""
    try:
        csv_path = dataset_manager.export_csv(dataset_id)
        return FileResponse(
            csv_path,
            media_type="text/csv",
            filename=f"{dataset_id}.csv",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
