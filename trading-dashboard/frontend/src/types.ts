export type AssetType = 'STOCKS' | 'CRYPTO'

export interface Candle {
  time: number // Unix timestamp in seconds
  open: number
  high: number
  low: number
  close: number
  volume: number
  symbol?: string
  asset_type?: AssetType
  is_final?: boolean
}

export interface SMAPoint {
  time: number
  value: number
}

export interface TradingSignal {
  id: string
  symbol: string
  signal: 'BUY' | 'SELL'
  timestamp: string // ISO string
  event_time?: number // Unix timestamp in seconds
  price: number
  sentiment_score?: number
  sma_20?: number
  sma_50?: number
  order_status?: string
  order_id?: string
  source?: string
  asset_type?: AssetType
}

export interface NewsItem {
  id: string
  symbol: string
  headline: string
  summary: string
  created_at: string
  sentiment_score: number
  sentiment_label: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  url?: string
  asset_type?: AssetType
}

export interface PaperAccount {
  id?: string
  account_number?: string
  equity: number
  cash: number
  buying_power: number
  currency: string
  status: string
  pattern_day_trader: boolean
}

export interface PaperPosition {
  symbol: string
  qty: number
  side?: string
  avg_entry_price: number
  market_value: number
  cost_basis?: number
  unrealized_pl: number
  unrealized_plpc: number
  current_price: number
}

export interface PaperOrder {
  id: string
  client_order_id: string
  symbol: string
  qty: number
  filled_qty: number
  side: string
  type: string
  time_in_force: string
  status: string
  submitted_at: string
  filled_at?: string
  filled_avg_price?: number
}

export interface ProducerHealthInfo {
  status?: string
  pid?: number
  uptime_sec?: number
  active?: boolean
  error_count?: number
}

export interface PipelineStatus {
  redpanda_connected: boolean
  brokers: string[]
  topics: {
    stock_prices: number
    market_news: number
    trading_signals: number
    crypto_bars_1m?: number
    crypto_trades?: number
    crypto_news?: number
    crypto_signals?: number
  }
  flink_status: 'RUNNING' | 'FAILED' | 'RESTARTING' | 'UNKNOWN'
  flink_job_id?: string
  crypto_flink_status?: 'RUNNING' | 'FAILED' | 'RESTARTING' | 'UNKNOWN'
  crypto_flink_job_id?: string
  last_event_timestamps: {
    stock_prices?: string
    market_news?: string
    trading_signals?: string
    crypto_bars_1m?: string
    crypto_trades?: string
    crypto_news?: string
    crypto_signals?: string
  }
  last_ingestion_timestamps?: {
    stock_prices?: string
    market_news?: string
    trading_signals?: string
    crypto_bars_1m?: string
    crypto_trades?: string
    crypto_news?: string
    crypto_signals?: string
  }
  last_candle_timestamp?: string
  last_crypto_candle_timestamp?: string
  last_ingestion_timestamp?: string
  producer_status?: {
    price_producer?: ProducerHealthInfo
    news_producer?: ProducerHealthInfo
    crypto_producer?: ProducerHealthInfo
    crypto_handler?: ProducerHealthInfo
  }
  active_ws_clients: number
  market_status: 'LIVE STREAMING' | 'DELAYED DATA' | 'HISTORICAL REPLAY' | 'STALE' | 'MARKET CLOSED' | 'RECONNECTING' | 'ERROR'
  market_delay_minutes: number
  latency_label?: string
  crypto_mode?: string
  crypto_latency_label?: string
  crypto_latency_sec?: number
  pipeline_verdict?: 'HEALTHY' | 'DEGRADED' | 'STALE' | 'DOWN' | 'UNKNOWN' | string
  pipeline_verdict_label?: string
  health_pillars?: {
    infrastructure?: { status: string; reason: string }
    data_freshness?: { status: string; reason: string }
    processing?: { status: string; reason: string }
    signal_handlers?: { status: string; reason: string }
    end_to_end?: { status: string; reason: string }
  }
}

export type Timeframe = '1m' | '5m' | '15m' | '1h'

export type DashboardTab = 'terminal' | 'analytics' | 'portfolio' | 'workbench' | 'paper_bot' | 'backtesting' | 'observability' | 'reliability'

export interface WorkbenchAccount {
  id: string
  account_number: string
  status: string
  currency: string
  cash: number
  equity: number
  portfolio_value: number
  buying_power: number
  initial_margin: number
  maintenance_margin: number
  pattern_day_trader: boolean
  is_mock: boolean
  broker: string
  updated_at: string
}

export interface WorkbenchPosition {
  symbol: string
  qty: number
  side: string
  avg_entry_price: number
  current_price: number
  market_value: number
  unrealized_pl: number
  unrealized_plpc: number
  asset_class: string
  is_mock: boolean
}

export interface WorkbenchOrder {
  id: string
  client_order_id: string
  created_at: string
  updated_at: string
  submitted_at: string
  filled_at?: string | null
  expired_at?: string | null
  canceled_at?: string | null
  failed_at?: string | null
  replaced_at?: string | null
  replaced_by?: string | null
  replaces?: string | null
  asset_class: string
  symbol: string
  qty?: number | null
  notional?: number | null
  filled_qty: number
  filled_avg_price?: number | null
  order_class: string
  order_type: string
  type: string
  side: string
  time_in_force: string
  limit_price?: number | null
  stop_price?: number | null
  trail_price?: number | null
  trail_percent?: number | null
  status: string
  is_mock: boolean
  broker: string
}

export interface WorkbenchActivity {
  id: string
  timestamp: string
  activity_type: string
  order_id: string
  description: string
  metadata?: Record<string, any>
  is_mock: boolean
}

export interface StrategyMetric {
  strategy_id: number
  strategy_name: string
  short_title: string
  tag: string
  description: string
  is_production: boolean
  status: string
  asset: string
  split: string
  total_return_pct: number
  benchmark_return_pct: number
  alpha_pct: number
  max_drawdown_pct: number
  sharpe_ratio: string
  total_trades: number
  win_rate_pct: number
  profit_factor: number
  total_fees_usd: number
  total_slippage_usd: number
  sample_size_warning: boolean
  sample_size_message: string | null
  data_source_mode: string
}

export interface EquityCurvePoint {
  time: number
  equity: number
  drawdown_pct: number
  benchmark_close: number
}

export interface EquityCurveData {
  asset: string
  strategy_id: number
  strategy_name: string
  initial_capital: number
  final_equity: number
  points_count: number
  points: EquityCurvePoint[]
  data_mode: string
}

export interface HistoricalTrade {
  trade_id: number
  asset: string
  strategy: string
  split: string
  side: string
  entry_bar: number
  exit_bar: number
  holding_bars: number
  entry_price: number
  exit_price: number
  qty: number
  pnl: number
  pnl_pct: number
  fees: number
  slippage: number
  exit_time?: number
}

export interface SplitPerformance {
  split: string
  split_label: string
  bars: number
  total_return_pct: number
  benchmark_return_pct: number
  alpha_pct: number
  max_drawdown_pct: number
  trades: number
  win_rate_pct: number
  sharpe_ratio: string
}

export interface StreamingObservabilityData {
  timestamp: number
  pipeline_verdict: 'HEALTHY' | 'DEGRADED' | 'STALE' | 'DOWN' | 'UNKNOWN' | string
  pipeline_verdict_label: string
  health_pillars?: {
    infrastructure?: { status: string; reason: string }
    data_freshness?: { status: string; reason: string }
    processing?: { status: string; reason: string }
    signal_handlers?: { status: string; reason: string }
    end_to_end?: { status: string; reason: string }
  }
  health_issues: string[]
  kafka: {
    connected: boolean
    brokers: string[]
    topics: Record<string, { partition: number; end_offset: number; messages_total: number }>
    consumer_lag: {
      stocks_handler: { group: string; topic: string; committed: number; end_offset: number; lag: number }
      crypto_handler: { group: string; topic: string; committed: number; end_offset: number; lag: number }
    }
  }
  flink: {
    connected: boolean
    jobs: {
      stocks_job: {
        jid: string
        name: string
        state: string
        tasks_running: number
        tasks_total: number
        checkpoints: {
          total_checkpoints: number
          completed_checkpoints: number
          failed_checkpoints: number
          in_progress_checkpoints: number
          latest_checkpoint_id: number
          latest_checkpoint_duration_ms: number
          latest_checkpoint_size_bytes: number
          latest_checkpoint_path: string
          latest_ack_timestamp?: number
        }
      } | null
      crypto_job: {
        jid: string
        name: string
        state: string
        tasks_running: number
        tasks_total: number
        checkpoints: {
          total_checkpoints: number
          completed_checkpoints: number
          failed_checkpoints: number
          in_progress_checkpoints: number
          latest_checkpoint_id: number
          latest_checkpoint_duration_ms: number
          latest_checkpoint_size_bytes: number
          latest_checkpoint_path: string
          latest_ack_timestamp?: number
        }
      } | null
    }
  }
  producers: Record<string, ProducerHealthInfo & { heartbeat_age_sec?: number }>
  latency: {
    stocks: {
      last_event_ts?: number
      latency_sec?: number
      status: string
      status_label: string
    }
    crypto: {
      last_event_ts?: number
      latency_sec?: number
      status: string
      status_label: string
    }
  }
}

export interface ReliabilityData {
  recovery: {
    status: string
    timestamp: string | null
    actions_taken: string[]
    total_actions: number
  }
  slack_outbox: {
    summary: {
      total: number
      pending: number
      delivered: number
      failed: number
    }
    recent_messages: Array<{
      timestamp: number
      iso_time: string
      signal_id: string
      dedup_key: string
      status: string
      slack_ts?: string
    }>
  }
  dead_letter_queue: {
    total_count: number
    records: Array<{
      timestamp: number
      iso_time: string
      signal_id: string
      dedup_key: string
      error: string
      retriable: boolean
      status: string
    }>
  }
  deduplication: {
    persisted_signals_count: number
    keys: string[]
  }
}

export interface PortfolioSummary {
  status?: 'ACTIVE' | 'DEGRADED_LAST_KNOWN_GOOD' | 'UNAVAILABLE' | string
  is_fallback?: boolean
  fallback_reason?: string
  source_timestamp?: string
  source_timestamp_sec?: number
  cache_age_sec?: number
  account_id?: string
  error?: string
  account: PaperAccount | null
  positions_count: number
  total_unrealized_pl: number
  total_unrealized_plpc: number
  total_cost_basis: number
  open_orders_count: number
  filled_orders_count: number
  recent_orders_count: number
  positions: PaperPosition[]
  recent_orders: PaperOrder[]
}

// ============================================================================
// V2 PAPER TRADING BOT TYPES (GĐ35)
// ============================================================================

export interface V2BotSummary {
  session_id: string
  bot_id: string
  bot_name: string
  strategy_id: string
  strategy_version: string
  symbols: string[]
  timeframe: string
  lifecycle_state: 'STARTING' | 'RUNNING' | 'PAUSED' | 'STOPPING' | 'STOPPED' | 'ERROR' | string
  status: string
  initial_cash: number
  current_equity: number
  cash: number
  available_cash: number
  reserved_cash: number
  market_value: number
  unrealized_pnl: number
  realized_pnl: number
  open_positions_count: number
  started_at: string | null
  paused_at: string | null
  stopped_at: string | null
  last_heartbeat_at: string | null
  error_code: string | null
  error_message: string | null
  risk_config_hash: string
  trading_mode: string
  environment: string
}

export interface V2Position {
  symbol: string
  qty: number
  avg_entry_price: number
  current_price: number
  cost_basis: number
  market_value: number
  unrealized_pnl: number
  realized_pnl: number
  environment: string
}

export interface V2Portfolio {
  session_id: string
  portfolio_id: string
  state: string
  initial_cash: number
  cash: number
  available_cash: number
  reserved_cash: number
  equity: number
  market_value: number
  unrealized_pnl: number
  realized_pnl: number
  positions: V2Position[]
  environment: string
}

export interface V2SimulatedOrder {
  simulated_order_id: string
  bot_session_id: string
  symbol: string
  side: 'BUY' | 'SELL' | string
  order_type: 'MARKET' | 'LIMIT' | 'STOP' | string
  quantity: number
  filled_quantity: number
  remaining_quantity: number
  average_fill_price: number
  status: string
  limit_price?: number | null
  stop_price?: number | null
  submitted_at: string | null
  filled_at: string | null
  cancelled_at: string | null
  rejection_reason?: string | null
  environment: string
}

export interface V2SimulatedFill {
  simulated_fill_id: string
  simulated_order_id: string
  symbol: string
  side: string
  fill_price: number
  fill_qty: number
  fee: number
  slippage: number
  fill_time: string
  source_bar_key: string
  execution_bar_key: string
  environment: string
}

export interface V2Performance {
  session_id: string
  report_generated_at: string
  capital_metrics: {
    initial_equity: number
    current_equity: number
    cash: number
    available_cash: number
    reserved_cash: number
    market_value: number
  }
  pnl_metrics: {
    realized_pnl: number
    unrealized_pnl: number
    gross_pnl: number
    total_fees: number
    estimated_slippage: number
    net_pnl: number
    return_pct: number
  }
  drawdown_metrics: {
    peak_equity: number
    drawdown_amount: number
    current_drawdown_pct: number
  }
  signal_metrics: {
    signals_received: number
    signals_accepted: number
    signals_rejected: number
  }
  order_metrics: {
    total_orders: number
    filled_orders: number
    partially_filled_orders: number
    cancelled_orders: number
    expired_orders: number
    fill_rate_pct: number
    total_filled_quantity: number
    turnover: number
  }
  financial: {
    initial_equity: number
    current_equity: number
    total_return_pct: number
    realized_pnl: number
    unrealized_pnl: number
  }
  signals: {
    signals_received: number
    signals_accepted: number
    signals_rejected: number
    acceptance_rate_pct: number
  }
  environment: string
}

export interface V2Health {
  session_id: string
  lifecycle_state: string
  overall_status: string
  last_heartbeat_age_seconds: number
  events_processed_count: number
  event_processing_latency_ms: number
  queue_depth: number
  consumer_health: string
  strategy_engine_health: string
  simulation_broker_health: string
  reconciliation_status: string
  error_count: number
  last_error?: string | null
  environment: string
}

export interface V2BacktestRun {
  run_id: string
  config: {
    backtest_run_id: string
    strategy_id: string
    strategy_version: string
    symbols: string[]
    timeframe: string
    initial_simulated_cash: number
    fee_model: string
    slippage_model: string
    warmup_bars_count: number
    seed?: number
    config_hash: string
    environment: string
  }
  metrics: {
    initial_equity: number
    final_equity: number
    net_pnl: number
    gross_pnl: number
    realized_pnl: number
    unrealized_pnl: number
    net_return_pct: number
    peak_equity: number
    max_drawdown_usd: number
    max_drawdown_pct: number
    total_fees: number
    total_slippage: number
    turnover_usd: number
    total_orders: number
    filled_orders: number
    total_fills: number
    total_trades: number
    winning_trades: number
    losing_trades: number
    win_rate_pct: number
    profit_factor: number | null
    time_in_market_pct: number
    sharpe_ratio: number | null
    sortino_ratio: number | null
    annualization_sampling: string
    annualization_factor: number
    disclaimer: string
    environment: string
  }
  deterministic_fingerprint: string
  orders_count: number
  fills_count: number
  equity_points_count: number
  positions?: any[]
  dataset?: {
    dataset_id: string
    provider: string
    source_type: string
    feed: string
    asset_class: string
    timeframe?: string
    total_bars: number
    checksum_sha256: string
    start_time: string
    end_time: string
    requested_start?: string
    requested_end?: string
    is_synthetic: boolean
    duplicate_count?: number
    gap_count?: number
    adjustment_policy?: string
    completeness_status?: string
  }
  data_source?: string
  closed_trades_count?: number
  started_at: string
  completed_at: string
  environment: string
}

export interface BacktestChartCandle {
  time: number
  timestamp: string
  ny_time?: string
  session?: 'RTH' | 'PRE_MARKET' | 'AFTER_HOURS' | 'CLOSED' | 'CRYPTO_24_7' | string
  symbol: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  is_warmup: boolean
  bar_key?: string
}

export interface BacktestIndicatorPoint {
  time: number
  timestamp: string
  value: number | null
  warmup_complete: boolean
}

export interface BacktestStrategySignal {
  signal_id: string
  strategy_id?: string
  strategy_version?: string
  symbol: string
  signal_type: 'BUY' | 'SELL' | 'HOLD' | 'NO_SIGNAL' | string
  strength: number
  price?: number
  reason?: string
  reason_codes?: string[]
  indicator_values?: Record<string, any>
  source_bar_key?: string
  decision_id?: string
  decision_status?: string
  timestamp: string
  time?: number
}

export interface BacktestSimulatedFill {
  simulated_fill_id: string
  simulated_order_id: string
  intent_id?: string
  signal_id?: string
  strategy_id?: string
  strategy_reason?: string
  reason_codes?: string[]
  order_type?: string
  order_status?: string
  is_partial_fill?: boolean
  symbol: string
  side: 'BUY' | 'SELL' | string
  fill_price: number
  fill_qty: number
  fee: number
  slippage: number
  fill_time: string
  fill_epoch?: number
  source_bar_key?: string
  execution_bar_key?: string
  assumptions?: string
  environment: string
}

export interface BacktestClosedTrade {
  trade_id: string
  symbol: string
  direction: 'LONG' | 'SHORT' | string
  entry_fill_ids: string[]
  exit_fill_id: string
  entry_order_ids: string[]
  exit_order_id: string
  entry_time: string
  exit_time: string
  entry_epoch: number
  exit_epoch: number
  entry_price: number
  exit_price: number
  qty: number
  gross_pnl: number
  fees: number
  slippage: number
  net_pnl: number
  return_pct: number
  is_win: boolean
  duration_seconds: number
  entry_reason?: string
  exit_reason?: string
  strategy_id?: string
}

export interface BacktestPortfolioTransaction {
  transaction_id: string
  portfolio_id: string
  timestamp: string
  transaction_type: string
  amount: number
  cash_after: number
  description: string
  reference_id: string
  environment: string
}

export interface BacktestChartBundle {
  run_id: string
  config: V2BacktestRun['config'] & { execution_config?: Record<string, any> }
  dataset_manifest?: V2BacktestRun['dataset'] | null
  data_source: string
  environment: string
  trading_mode: string
  paper_execution_gate: string
  symbols: string[]
  timeframe: string
  warmup_bars_count: number
  session_policy?: 'STRICT_HOURS' | 'ALL_HOURS' | string
  session_counts?: Record<string, number>
  gap_summary?: {
    total_gaps: number
    non_trading_session: number
    extended_hours_no_trade: number
    rth_missing: number
    feed_gap: number
  }
  indicator_readiness?: Record<string, {
    total_bars: number
    ma_fast_ready_bar: number | null
    ma_slow_ready_bar: number | null
    rsi_ready_bar: number | null
    ma_fast_ready_time?: string | null
    ma_slow_ready_time?: string | null
    rsi_ready_time?: string | null
  }>
  requested_window?: {
    start?: string | null
    end?: string | null
    session_policy?: string
    source_dataset_id?: string | null
  }
  actual_window?: {
    first_bar?: string | null
    last_bar?: string | null
    candles_count: number
    manifest_total_bars?: number | null
    warmup_bars_count: number
  }
  data_quality_warnings?: string[]
  candles: BacktestChartCandle[]
  indicators: {
    strategy_id?: string
    params: {
      fast_period: number
      slow_period: number
      rsi_period: number
      rsi_method: string
      rsi_oversold: number
      rsi_overbought: number
    }
    series_by_symbol: Record<string, {
      ma_fast: BacktestIndicatorPoint[]
      ma_slow: BacktestIndicatorPoint[]
      rsi: BacktestIndicatorPoint[]
    }>
  }
  signals: BacktestStrategySignal[]
  decisions: any[]
  orders: any[]
  fills: BacktestSimulatedFill[]
  portfolio_transactions: BacktestPortfolioTransaction[]
  closed_trades: BacktestClosedTrade[]
  gaps: Array<{
    symbol: string
    gap_start: string
    gap_end: string
    gap_duration_seconds: number
    missing_bars_estimated: number
    gap_type?: 'NON_TRADING_SESSION' | 'EXTENDED_HOURS_NO_TRADE' | 'RTH_NO_TRADE_OR_MISSING' | 'FEED_GAP' | string
    session_context?: string
  }>
  equity_curve: any[]
  metrics: V2BacktestRun['metrics']
  deterministic_fingerprint: string
}



export interface V2SupervisorOverview {
  status: string
  active_bots_count: number
  total_registered_bots?: number
  bot_counts_by_state?: {
    RUNNING: number
    PAUSED: number
    STOPPED: number
    ERROR: number
  }
  aggregate_simulation_capital?: {
    total_simulated_cash: number
    total_simulated_equity: number
    total_unrealized_pnl: number
    total_realized_pnl: number
    disclaimer: string
  }
  aggregate_orders?: {
    total_open_orders: number
    total_fills: number
  }
  dispatcher?: {
    total_received: number
    total_dispatched: number
    total_dropped: number
    total_duplicates: number
    active_queues_count: number
  }
  environment: string
  trading_mode: string
  paper_execution_gate: string
}

export interface StrategyPreset {
  preset_id: string
  preset_name: string
  strategy_id: string
  strategy_version: string
  parameters: Record<string, any>
  configuration_hash: string
  schema_version: string
  environment: string
  is_immutable: boolean
  locked_by_run?: string | null
  created_at: string
}

export interface ExperimentVariant {
  variant_id: string
  variant_name: string
  preset_id: string
  strategy_id: string
  parameters: Record<string, any>
  strategy_hash: string
  dataset_hash: string
  date_range: { start_time?: string; end_time?: string }
  initial_capital: number
  run_id?: string
  fingerprint?: string
  status: string
  metrics?: Record<string, any>
  error_message?: string
}

export interface BacktestExperiment {
  experiment_id: string
  name: string
  description?: string
  base_strategy_id: string
  dataset_version: string
  date_range?: { start_time?: string; end_time?: string }
  variants: ExperimentVariant[]
  status: string
  max_concurrency: number
  created_at: string
  completed_at?: string
  comparison_summary?: any
}

export interface ComparisonRow {
  run_id: string
  name: string
  preset_id: string
  strategy_id: string
  is_baseline: boolean
  is_comparable: boolean
  comparability_status: string
  comparability_reasons: string[]
  total_return_pct: number
  sharpe_ratio: number
  sortino_ratio: number
  max_drawdown_pct: number
  win_rate_pct: number
  total_trades: number
  profit_factor: number
  delta_sharpe: number
  delta_return_pct: number
  delta_max_drawdown_pct: number
  delta_win_rate_pct: number
  delta_profit_factor: number
}
