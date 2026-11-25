"""
libs/alpaca_paper_sdk.py — Comprehensive Alpaca Paper Trading & Data SDK Adapter (GĐ16.1)
Implements and bridges all API capabilities from 'Alpaca Markets Paper Trading_Dec2024.pdf'
using the official alpaca-py library with strict DRY_RUN safety guards.
"""

import os
import sys
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timezone
from uuid import UUID

# Ensure libs path is configured
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LIBS_DIR = os.path.join(BASE_DIR, 'libs')
if LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

from alpaca_config.keys import config

# Official alpaca-py imports
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
    TrailingStopOrderRequest,
    GetOrdersRequest,
    ReplaceOrderRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus, OrderStatus
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockTradesRequest,
    StockQuotesRequest,
    StockLatestQuoteRequest,
    StockLatestTradeRequest,
    StockSnapshotRequest,
    CryptoBarsRequest,
    CryptoTradesRequest,
    CryptoQuoteRequest,
    CryptoLatestQuoteRequest,
    CryptoLatestTradeRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from alpaca.trading.stream import TradingStream
from alpaca.data.live.stock import StockDataStream
from alpaca.data.live.crypto import CryptoDataStream
import requests

logger = logging.getLogger('alpaca-paper-sdk')


class AlpacaPaperSDK:
    """
    Unified client providing full coverage of Alpaca Markets Paper Trading Guide (Dec 2024).
    Features:
      1. TradingClient (Account, Configurations, Positions, Orders, Replace, Cancel).
      2. Historical Data (Stock & Crypto Bars, Trades, Quotes, Latest, Snapshots).
      3. WebSocket Streaming (StockDataStream, CryptoDataStream, TradingStream).
      4. Strict Dry-Run Safety Guards preventing unintended real order executions.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: bool = True,
        dry_run_orders: bool = True,
    ):
        self.api_key = api_key or config.get('key_id', os.environ.get('ALPACA_KEY_ID', ''))
        self.secret_key = secret_key or config.get('secret_key', os.environ.get('ALPACA_SECRET_KEY', ''))
        self.paper = paper
        self.dry_run_orders = dry_run_orders
        self.paper_base_url = config.get(
            'trade_api_base_url',
            os.environ.get('ALPACA_TRADE_BASE_URL', 'https://paper-api.alpaca.markets')
        )

        # Initialize alpaca-py clients
        if self.api_key and self.secret_key:
            self.trading_client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper
            )
            self.stock_data_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key
            )
            self.crypto_data_client = CryptoHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key
            )
        else:
            self.trading_client = None
            self.stock_data_client = None
            self.crypto_data_client = None

    # =========================================================================
    # Part 1: Account & Positions
    # =========================================================================

    def get_account(self) -> Any:
        """Retrieve Paper account information via official TradingClient."""
        if not self.trading_client:
            raise ValueError("TradingClient not initialized: missing API credentials.")
        return self.trading_client.get_account()

    def get_account_configurations(self) -> Dict[str, Any]:
        """
        Retrieve account configurations.
        Includes robust fallback: alpaca-py model requires dtbp_check/pdt_check which
        Alpaca API removed in late 2024. If model validation fails, queries REST endpoint.
        """
        if not self.trading_client:
            raise ValueError("TradingClient not initialized: missing API credentials.")
        try:
            return self.trading_client.get_account_configurations()
        except Exception as e:
            logger.info("Falling back to raw REST for account configurations due to: %s", e)
            headers = {
                'APCA-API-KEY-ID': self.api_key,
                'APCA-API-SECRET-KEY': self.secret_key,
            }
            resp = requests.get(f"{self.paper_base_url}/v2/account/configurations", headers=headers, timeout=5)
            resp.raise_for_status()
            return resp.json()

    def get_all_positions(self) -> List[Any]:
        """Retrieve all open positions."""
        if not self.trading_client:
            raise ValueError("TradingClient not initialized: missing API credentials.")
        return self.trading_client.get_all_positions()

    def get_open_position(self, symbol_or_asset_id: str) -> Any:
        """Fetch an individual open position by symbol or asset ID."""
        if not self.trading_client:
            raise ValueError("TradingClient not initialized: missing API credentials.")
        return self.trading_client.get_open_position(symbol_or_asset_id=symbol_or_asset_id)

    # =========================================================================
    # Part 2: Order Management & Execution Safeguards
    # =========================================================================

    def submit_order(
        self,
        order_data: Union[
            MarketOrderRequest,
            LimitOrderRequest,
            StopOrderRequest,
            StopLimitOrderRequest,
            TrailingStopOrderRequest,
        ],
        mock_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Submit order with strict DRY_RUN safety.
        In dry_run_orders mode (default), validates the order request object structure
        and returns a deterministic mock confirmation without sending HTTP request to Alpaca.
        """
        if self.dry_run_orders:
            # Validate order_data type
            valid_types = (
                MarketOrderRequest,
                LimitOrderRequest,
                StopOrderRequest,
                StopLimitOrderRequest,
                TrailingStopOrderRequest,
            )
            if not isinstance(order_data, valid_types):
                raise TypeError(f"Invalid order request type: {type(order_data)}")

            # Generate mock confirmation with verified request attributes
            mock_id = "mock-ord-" + os.urandom(4).hex()
            qty = getattr(order_data, 'qty', None)
            notional = getattr(order_data, 'notional', None)
            return {
                "id": mock_id,
                "client_order_id": getattr(order_data, 'client_order_id', f"dry-run-{mock_id}"),
                "symbol": getattr(order_data, 'symbol', ''),
                "qty": str(qty) if qty is not None else None,
                "notional": str(notional) if notional is not None else None,
                "side": str(getattr(order_data, 'side', '')),
                "type": type(order_data).__name__,
                "time_in_force": str(getattr(order_data, 'time_in_force', '')),
                "limit_price": getattr(order_data, 'limit_price', None),
                "stop_price": getattr(order_data, 'stop_price', None),
                "trail_percent": getattr(order_data, 'trail_percent', None),
                "status": "dry_run_accepted",
                "is_dry_run": True,
            }

        # Real order submission ONLY if dry_run_orders is explicitly False AND paper URL verified
        if 'paper-api' not in self.paper_base_url:
            raise RuntimeError("CRITICAL SAFETY BLOCK: Real submission blocked on non-paper endpoint.")
        return self.trading_client.submit_order(order_data=order_data)

    def get_order_by_id(self, order_id: Union[str, UUID]) -> Any:
        """Query order status by order ID."""
        if not self.trading_client:
            raise ValueError("TradingClient not initialized.")
        return self.trading_client.get_order_by_id(order_id)

    def get_orders(
        self,
        status: QueryOrderStatus = QueryOrderStatus.ALL,
        side: Optional[OrderSide] = None,
        symbols: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[Any]:
        """Fetch and filter orders using GetOrdersRequest."""
        if not self.trading_client:
            raise ValueError("TradingClient not initialized.")
        req = GetOrdersRequest(
            status=status,
            side=side,
            symbols=symbols,
            limit=limit,
        )
        return self.trading_client.get_orders(filter=req)

    def replace_order(
        self,
        order_id: Union[str, UUID],
        order_data: ReplaceOrderRequest,
    ) -> Dict[str, Any]:
        """Modify an existing order using ReplaceOrderRequest."""
        if self.dry_run_orders:
            return {
                "id": f"replaced-{order_id}",
                "previous_id": str(order_id),
                "qty": getattr(order_data, 'qty', None),
                "limit_price": getattr(order_data, 'limit_price', None),
                "status": "dry_run_replaced",
                "is_dry_run": True,
            }
        return self.trading_client.replace_order_by_id(order_id=order_id, order_data=order_data)

    def cancel_order_by_id(self, order_id: Union[str, UUID]) -> Dict[str, Any]:
        """Cancel a specific order by ID."""
        if self.dry_run_orders:
            return {
                "id": str(order_id),
                "status": "dry_run_canceled",
                "is_dry_run": True,
            }
        return self.trading_client.cancel_order_by_id(order_id=order_id)

    def cancel_all_orders(self) -> List[Dict[str, Any]]:
        """Cancel all open orders."""
        if self.dry_run_orders:
            return [{
                "status": "dry_run_canceled_all",
                "is_dry_run": True,
            }]
        return self.trading_client.cancel_orders()

    # =========================================================================
    # Part 3: Historical Market Data
    # =========================================================================

    def get_stock_bars(
        self,
        symbols: Union[str, List[str]],
        timeframe: TimeFrame,
        start: datetime,
        end: Optional[datetime] = None,
        feed: DataFeed = DataFeed.IEX,
    ) -> Any:
        """Fetch historical stock bars for single or multiple symbols."""
        if not self.stock_data_client:
            raise ValueError("StockHistoricalDataClient not initialized.")
        req = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=timeframe,
            start=start,
            end=end,
            feed=feed,
        )
        return self.stock_data_client.get_stock_bars(req)

    def get_stock_trades(
        self,
        symbol: str,
        start: datetime,
        end: Optional[datetime] = None,
        feed: DataFeed = DataFeed.IEX,
    ) -> Any:
        """Fetch historical trades for a stock symbol."""
        if not self.stock_data_client:
            raise ValueError("StockHistoricalDataClient not initialized.")
        req = StockTradesRequest(
            symbol_or_symbols=symbol,
            start=start,
            end=end,
            feed=feed,
        )
        return self.stock_data_client.get_stock_trades(req)

    def get_stock_quotes(
        self,
        symbol: str,
        start: datetime,
        end: Optional[datetime] = None,
        feed: DataFeed = DataFeed.IEX,
    ) -> Any:
        """Fetch historical quotes for a stock symbol."""
        if not self.stock_data_client:
            raise ValueError("StockHistoricalDataClient not initialized.")
        req = StockQuotesRequest(
            symbol_or_symbols=symbol,
            start=start,
            end=end,
            feed=feed,
        )
        return self.stock_data_client.get_stock_quotes(req)

    def get_stock_latest_quote(self, symbol: str, feed: DataFeed = DataFeed.IEX) -> Any:
        """Fetch latest quote for a stock symbol."""
        if not self.stock_data_client:
            raise ValueError("StockHistoricalDataClient not initialized.")
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=feed)
        return self.stock_data_client.get_stock_latest_quote(req)

    def get_stock_latest_trade(self, symbol: str, feed: DataFeed = DataFeed.IEX) -> Any:
        """Fetch latest trade for a stock symbol."""
        if not self.stock_data_client:
            raise ValueError("StockHistoricalDataClient not initialized.")
        req = StockLatestTradeRequest(symbol_or_symbols=symbol, feed=feed)
        return self.stock_data_client.get_stock_latest_trade(req)

    def get_stock_snapshot(self, symbol: str, feed: DataFeed = DataFeed.IEX) -> Any:
        """Fetch snapshot (daily bar, prev daily bar, latest quote, latest trade) for a stock symbol."""
        if not self.stock_data_client:
            raise ValueError("StockHistoricalDataClient not initialized.")
        req = StockSnapshotRequest(symbol_or_symbols=symbol, feed=feed)
        return self.stock_data_client.get_stock_snapshot(req)

    def get_crypto_bars(
        self,
        symbols: Union[str, List[str]],
        timeframe: TimeFrame,
        start: datetime,
        end: Optional[datetime] = None,
    ) -> Any:
        """Fetch historical crypto bars."""
        if not self.crypto_data_client:
            raise ValueError("CryptoHistoricalDataClient not initialized.")
        req = CryptoBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=timeframe,
            start=start,
            end=end,
        )
        return self.crypto_data_client.get_crypto_bars(req)

    def get_crypto_trades(
        self,
        symbol: str,
        start: datetime,
        end: Optional[datetime] = None,
    ) -> Any:
        """Fetch historical crypto trades."""
        if not self.crypto_data_client:
            raise ValueError("CryptoHistoricalDataClient not initialized.")
        req = CryptoTradesRequest(
            symbol_or_symbols=symbol,
            start=start,
            end=end,
        )
        return self.crypto_data_client.get_crypto_trades(req)

    def get_crypto_latest_quote(self, symbol: str) -> Any:
        """Fetch latest quote for a crypto pair."""
        if not self.crypto_data_client:
            raise ValueError("CryptoHistoricalDataClient not initialized.")
        req = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
        return self.crypto_data_client.get_crypto_latest_quote(req)

    def get_crypto_latest_trade(self, symbol: str) -> Any:
        """Fetch latest trade for a crypto pair."""
        if not self.crypto_data_client:
            raise ValueError("CryptoHistoricalDataClient not initialized.")
        req = CryptoLatestTradeRequest(symbol_or_symbols=symbol)
        return self.crypto_data_client.get_crypto_latest_trade(req)

    # =========================================================================
    # Part 4: WebSocket Stream Constructors (Audit & Reference Implementations)
    # =========================================================================

    def create_stock_data_stream(self) -> StockDataStream:
        """Instantiate official alpaca-py StockDataStream."""
        return StockDataStream(
            api_key=self.api_key,
            secret_key=self.secret_key,
            feed=DataFeed.IEX,
        )

    def create_crypto_data_stream(self) -> CryptoDataStream:
        """Instantiate official alpaca-py CryptoDataStream."""
        return CryptoDataStream(
            api_key=self.api_key,
            secret_key=self.secret_key,
        )

    def create_trading_stream(self) -> TradingStream:
        """Instantiate official alpaca-py TradingStream for order updates."""
        return TradingStream(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=self.paper,
        )

