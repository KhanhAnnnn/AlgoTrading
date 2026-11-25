import React, { useState, useEffect, useRef, useCallback } from 'react'
import type {
  Candle,
  TradingSignal,
  NewsItem,
  PaperAccount,
  PaperPosition,
  PaperOrder,
  PipelineStatus,
  Timeframe,
  AssetType,
  DashboardTab,
} from './types'
import { TopBar } from './components/TopBar'
import { TradingChart } from './components/TradingChart'
import { NewsSentimentPanel } from './components/NewsSentimentPanel'
import { SignalHistoryPanel } from './components/SignalHistoryPanel'
import { PaperTradingPanel } from './components/PaperTradingPanel'
import { PipelineMonitorPanel } from './components/PipelineMonitorPanel'
import { SignalModal } from './components/SignalModal'
import { HistoricalReplayBar } from './components/HistoricalReplayBar'
import { StrategyAnalyticsPanel } from './components/StrategyAnalyticsPanel'
import { PortfolioPanel } from './components/PortfolioPanel'
import { StreamingObservabilityPanel } from './components/StreamingObservabilityPanel'
import { ReliabilityLogsPanel } from './components/ReliabilityLogsPanel'
import { TradingWorkbenchPanel } from './components/TradingWorkbenchPanel'
import { PaperBotPanel } from './components/PaperBotPanel'
import { BacktestPanel } from './components/BacktestPanel'
import { ErrorBoundary } from './components/ErrorBoundary'

const API_BASE = 'http://127.0.0.1:8005'
const WS_URL = 'ws://127.0.0.1:8005/ws/live'

export const App: React.FC = () => {
  // Navigation Tab State
  const [activeTab, setActiveTab] = useState<DashboardTab>('terminal')

  // Asset type & Selected symbol & timeframe
  const [assetType, setAssetType] = useState<AssetType>('STOCKS')
  const [symbol, setSymbol] = useState<string>('NVDA')
  const [timeframe, setTimeframe] = useState<Timeframe>('1m')

  // Live Market Data State
  const [candles, setCandles] = useState<Candle[]>([])
  const [signals, setSignals] = useState<TradingSignal[]>([])
  const [news, setNews] = useState<NewsItem[]>([])
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus | null>(null)

  // Alpaca Paper Trading State (Read-Only)
  const [paperAccount, setPaperAccount] = useState<PaperAccount | null>(null)
  const [paperPositions, setPaperPositions] = useState<PaperPosition[]>([])
  const [paperOrders, setPaperOrders] = useState<PaperOrder[]>([])
  const [paperLoading, setPaperLoading] = useState(false)

  // WebSocket Connection
  const [wsConnected, setWsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<any>(null)

  // Selected Signal for Modal
  const [selectedSignal, setSelectedSignal] = useState<TradingSignal | null>(null)

  // Historical Replay Mode State
  const [isReplayMode, setIsReplayMode] = useState(false)
  const [allReplayCandles, setAllReplayCandles] = useState<Candle[]>([])
  const [replayIndex, setReplayIndex] = useState(0)
  const [isReplayPlaying, setIsReplayPlaying] = useState(false)
  const [replaySpeed, setReplaySpeed] = useState(5)
  const replayIntervalRef = useRef<any>(null)

  // Price change calculation
  const currentPrice = candles.length > 0 ? candles[candles.length - 1].close : null
  const firstPrice = candles.length > 0 ? candles[0].open : currentPrice || 0
  const priceChange = currentPrice && firstPrice ? currentPrice - firstPrice : 0
  const priceChangePercent = firstPrice ? (priceChange / firstPrice) * 100 : 0

  // Asset type switcher
  const handleAssetTypeChange = (type: AssetType) => {
    setAssetType(type)
    if (type === 'CRYPTO') {
      setSymbol('BTC/USD')
    } else {
      setSymbol('NVDA')
    }
    if (isReplayMode) {
      setIsReplayMode(false)
      setIsReplayPlaying(false)
    }
  }

  // Symbol selector
  const handleSelectSymbol = (sym: string) => {
    setSymbol(sym)
    if (isReplayMode) {
      setIsReplayMode(false)
      setIsReplayPlaying(false)
    }
  }

  // 1. Fetch Initial REST Data for Symbol & Timeframe
  const fetchCandles = useCallback(async (sym: string, tf: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/candles?symbol=${encodeURIComponent(sym)}&timeframe=${tf}`)
      if (res.ok) {
        const data = await res.json()
        if (data.candles && Array.isArray(data.candles)) {
          setCandles(data.candles)
        }
      }
    } catch (err) {
      console.error('Failed to fetch candles:', err)
    }
  }, [])

  const fetchSignals = useCallback(async (sym?: string) => {
    try {
      const url = sym ? `${API_BASE}/api/signals?symbol=${encodeURIComponent(sym)}` : `${API_BASE}/api/signals`
      const res = await fetch(url)
      if (res.ok) {
        const data = await res.json()
        if (data.signals) {
          const mapped: TradingSignal[] = data.signals.map((s: any, idx: number) => ({
            id: `sig-${s.symbol}-${s.time}-${idx}`,
            symbol: s.symbol,
            signal: s.signal,
            timestamp: s.signal_time_str || new Date(s.time * 1000).toISOString(),
            event_time: s.time,
            price: s.price_at_signal,
            sentiment_score: s.sentiment ?? s.sentiment_score ?? 0.25,
            sma_20: s.sma_20,
            sma_50: s.sma_50,
            order_status: s.paper_order?.status || 'recorded',
            order_id: s.paper_order?.id,
            asset_type: s.asset_type || (s.symbol.includes('/') ? 'CRYPTO' : 'STOCKS'),
          }))
          setSignals(mapped)
        }
      }
    } catch (err) {
      console.error('Failed to fetch signals:', err)
    }
  }, [])

  const fetchNews = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/news`)
      if (res.ok) {
        const data = await res.json()
        if (data.news) {
          const mapped: NewsItem[] = data.news.map((n: any) => ({
            id: String(n.id || Math.random()),
            symbol: n.symbol,
            headline: n.headline,
            summary: n.summary || '',
            created_at: n.timestamp_iso || new Date(n.time * 1000).toISOString(),
            sentiment_score: n.sentiment ?? 0,
            sentiment_label:
              n.sentiment > 0.05
                ? 'BULLISH'
                : n.sentiment < -0.05
                ? 'BEARISH'
                : 'NEUTRAL',
            url: n.url,
            asset_type: n.asset_type || (n.symbol.includes('/') ? 'CRYPTO' : 'STOCKS'),
          }))
          setNews(mapped)
        }
      }
    } catch (err) {
      console.error('Failed to fetch news:', err)
    }
  }, [])

  const fetchSystemStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/system/status`)
      if (res.ok) {
        const data = await res.json()
        setPipelineStatus({
          redpanda_connected: data.kafka?.redpanda_connected ?? true,
          brokers: data.kafka?.brokers ?? ['localhost:9092'],
          topics: {
            stock_prices: data.kafka?.topic_counts?.['stock-prices'] ?? 0,
            market_news: data.kafka?.topic_counts?.['market-news'] ?? 0,
            trading_signals: data.kafka?.topic_counts?.['trading-signals'] ?? 0,
            crypto_bars_1m: data.kafka?.topic_counts?.['crypto-bars-1m'] ?? 0,
            crypto_trades: data.kafka?.topic_counts?.['crypto-trades'] ?? 0,
            crypto_news: data.kafka?.topic_counts?.['crypto-news'] ?? 0,
            crypto_signals: data.kafka?.topic_counts?.['crypto-signals'] ?? 0,
          },
          flink_status: data.flink?.streaming_job?.state || 'RUNNING',
          flink_job_id: data.flink?.streaming_job?.jid,
          crypto_flink_status: data.flink?.crypto_streaming_job?.state || 'RUNNING',
          crypto_flink_job_id: data.flink?.crypto_streaming_job?.jid,
          last_event_timestamps: {
            stock_prices: data.kafka?.last_event_timestamps?.['stock-prices']
              ? new Date(data.kafka.last_event_timestamps['stock-prices'] * 1000).toISOString()
              : undefined,
            market_news: data.kafka?.last_event_timestamps?.['market-news']
              ? new Date(data.kafka.last_event_timestamps['market-news'] * 1000).toISOString()
              : undefined,
            trading_signals: data.kafka?.last_event_timestamps?.['trading-signals']
              ? new Date(data.kafka.last_event_timestamps['trading-signals'] * 1000).toISOString()
              : undefined,
            crypto_bars_1m: data.kafka?.last_event_timestamps?.['crypto-bars-1m']
              ? new Date(data.kafka.last_event_timestamps['crypto-bars-1m'] * 1000).toISOString()
              : undefined,
            crypto_trades: data.kafka?.last_event_timestamps?.['crypto-trades']
              ? new Date(data.kafka.last_event_timestamps['crypto-trades'] * 1000).toISOString()
              : undefined,
            crypto_news: data.kafka?.last_event_timestamps?.['crypto-news']
              ? new Date(data.kafka.last_event_timestamps['crypto-news'] * 1000).toISOString()
              : undefined,
            crypto_signals: data.kafka?.last_event_timestamps?.['crypto-signals']
              ? new Date(data.kafka.last_event_timestamps['crypto-signals'] * 1000).toISOString()
              : undefined,
          },
          last_ingestion_timestamps: {
            stock_prices: data.kafka?.last_ingestion_timestamps?.['stock-prices']
              ? new Date(data.kafka.last_ingestion_timestamps['stock-prices'] * 1000).toISOString()
              : undefined,
            market_news: data.kafka?.last_ingestion_timestamps?.['market-news']
              ? new Date(data.kafka.last_ingestion_timestamps['market-news'] * 1000).toISOString()
              : undefined,
            trading_signals: data.kafka?.last_ingestion_timestamps?.['trading-signals']
              ? new Date(data.kafka.last_ingestion_timestamps['trading-signals'] * 1000).toISOString()
              : undefined,
          },
          last_candle_timestamp: data.last_candle_timestamp,
          last_crypto_candle_timestamp: data.last_crypto_candle_timestamp,
          last_ingestion_timestamp: data.last_ingestion_timestamp,
          producer_status: data.producer_status,
          active_ws_clients: data.kafka?.active_ws_clients ?? 1,
          market_status: data.data_mode || 'MARKET CLOSED',
          market_delay_minutes: Math.round((data.data_latency_sec || 0) / 60),
          latency_label: data.latency_label,
          crypto_mode: data.crypto_mode,
          crypto_latency_label: data.crypto_latency_label,
          crypto_latency_sec: data.crypto_latency_sec,
        })
      }
    } catch (err) {
      console.error('Failed to fetch system status:', err)
    }
  }, [])

  const fetchPaperData = useCallback(async () => {
    setPaperLoading(true)
    try {
      const [accRes, posRes, ordRes] = await Promise.all([
        fetch(`${API_BASE}/api/paper/account`),
        fetch(`${API_BASE}/api/paper/positions`),
        fetch(`${API_BASE}/api/paper/orders`),
      ])

      if (accRes.ok) {
        const acc = await accRes.json()
        setPaperAccount({
          account_number: acc.account_number || 'PAPER-ACCOUNT',
          equity: Number(acc.equity || 100000),
          cash: Number(acc.cash || 100000),
          buying_power: Number(acc.buying_power || 200000),
          currency: acc.currency || 'USD',
          status: acc.status || 'ACTIVE',
          pattern_day_trader: Boolean(acc.pattern_day_trader),
        })
      }

      if (posRes.ok) {
        const posData = await posRes.json()
        const posList = Array.isArray(posData) ? posData : Array.isArray(posData?.positions) ? posData.positions : []
        setPaperPositions(
          posList.map((p: any) => ({
            symbol: p.symbol,
            qty: Number(p.qty),
            avg_entry_price: Number(p.avg_entry_price),
            market_value: Number(p.market_value),
            cost_basis: Number(p.cost_basis),
            unrealized_pl: Number(p.unrealized_pl),
            unrealized_plpc: Number(p.unrealized_plpc),
            current_price: Number(p.current_price),
          }))
        )
      }

      if (ordRes.ok) {
        const ordData = await ordRes.json()
        const ordList = Array.isArray(ordData) ? ordData : Array.isArray(ordData?.orders) ? ordData.orders : []
        setPaperOrders(
          ordList.map((o: any) => ({
            id: o.id,
            client_order_id: o.client_order_id,
            symbol: o.symbol,
            qty: Number(o.qty),
            filled_qty: Number(o.filled_qty || 0),
            side: o.side,
            type: o.type,
            time_in_force: o.time_in_force,
            status: o.status,
            submitted_at: o.submitted_at,
            filled_at: o.filled_at,
            filled_avg_price: o.filled_avg_price ? Number(o.filled_avg_price) : undefined,
          }))
        )
      }
    } catch (err) {
      console.error('Failed to fetch paper data:', err)
    } finally {
      setPaperLoading(false)
    }
  }, [])

  // Initial load on symbol / timeframe change
  useEffect(() => {
    fetchCandles(symbol, timeframe)
    fetchSignals()
    fetchNews()
    fetchSystemStatus()
    fetchPaperData()
  }, [symbol, timeframe, fetchCandles, fetchSignals, fetchNews, fetchSystemStatus, fetchPaperData])

  // Periodic polling for status & paper trading
  useEffect(() => {
    const timer = setInterval(() => {
      fetchSystemStatus()
    }, 10000)
    return () => clearInterval(timer)
  }, [fetchSystemStatus])

  // Refs for stable WebSocket callbacks
  const symbolRef = useRef(symbol)
  useEffect(() => {
    symbolRef.current = symbol
  }, [symbol])

  const timeframeRef = useRef(timeframe)
  useEffect(() => {
    timeframeRef.current = timeframe
  }, [timeframe])

  const isReplayModeRef = useRef(isReplayMode)
  useEffect(() => {
    isReplayModeRef.current = isReplayMode
  }, [isReplayMode])

  // Handle incoming WebSocket messages
  const handleIncomingWSMessage = useCallback((msg: any) => {
    const eventType = msg.type || msg.event

    if ((eventType === 'candle' || eventType === 'crypto_candle') && !isReplayModeRef.current) {
      const data = msg.data
      if (data && (data.symbol === symbolRef.current || data.symbol?.replace('-', '/') === symbolRef.current)) {
        setCandles((prev) => {
          if (!prev.length) return [data]
          const last = prev[prev.length - 1]
          if (last.time === data.time) {
            const updated = [...prev]
            updated[updated.length - 1] = {
              ...last,
              high: Math.max(last.high, data.high),
              low: Math.min(last.low, data.low),
              close: data.close,
              volume: last.volume + (data.volume || 0),
            }
            return updated
          } else if (data.time > last.time) {
            return [...prev, data]
          }
          return prev
        })
      }
    } else if (eventType === 'crypto_trade' && !isReplayModeRef.current) {
      const t = msg.data
      if (t && (t.symbol === symbolRef.current || t.symbol?.replace('-', '/') === symbolRef.current)) {
        setCandles((prev) => {
          if (!prev.length) return prev
          const last = { ...prev[prev.length - 1] }
          last.close = t.price
          last.high = Math.max(last.high, t.price)
          last.low = Math.min(last.low, t.price)
          last.volume = last.volume + (t.size || 0)
          const updated = [...prev]
          updated[updated.length - 1] = last
          return updated
        })
      }
    } else if (eventType === 'signal' || eventType === 'crypto_signal') {
      const s = msg.data
      const newSignal: TradingSignal = {
        id: `sig-${s.symbol}-${s.time}-${Date.now()}`,
        symbol: s.symbol,
        signal: s.signal,
        timestamp: s.signal_time_str || new Date(s.time * 1000).toISOString(),
        event_time: s.time,
        price: s.price_at_signal,
        sentiment_score: s.sentiment ?? s.sentiment_score ?? 0.25,
        sma_20: s.sma_20,
        sma_50: s.sma_50,
        order_status: s.paper_order?.status || 'accepted',
        order_id: s.paper_order?.id,
        asset_type: s.asset_type || (s.symbol?.includes('/') ? 'CRYPTO' : 'STOCKS'),
      }
      setSignals((prev) => [newSignal, ...prev])
      fetchPaperData()
    } else if (eventType === 'news' || eventType === 'crypto_news') {
      const n = msg.data
      const newNews: NewsItem = {
        id: String(n.id || Date.now()),
        symbol: n.symbol,
        headline: n.headline,
        summary: n.summary || '',
        created_at: n.timestamp_iso || new Date(n.time * 1000).toISOString(),
        sentiment_score: n.sentiment ?? 0,
        sentiment_label:
          n.sentiment > 0.05
            ? 'BULLISH'
            : n.sentiment < -0.05
            ? 'BEARISH'
            : 'NEUTRAL',
        url: n.url,
        asset_type: n.asset_type || (n.symbol?.includes('/') ? 'CRYPTO' : 'STOCKS'),
      }
      setNews((prev) => [newNews, ...prev.slice(0, 99)])
    }
  }, [fetchPaperData])

  const handleIncomingWSMessageRef = useRef(handleIncomingWSMessage)
  useEffect(() => {
    handleIncomingWSMessageRef.current = handleIncomingWSMessage
  }, [handleIncomingWSMessage])

  // 2. WebSocket Connection with Reconnection
  useEffect(() => {
    let isMounted = true

    const connectWebSocket = () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }

      if (wsRef.current) {
        if (wsRef.current.readyState === WebSocket.OPEN) {
          return
        }
        try {
          wsRef.current.onopen = null
          wsRef.current.onclose = null
          wsRef.current.onerror = null
          wsRef.current.onmessage = null
          wsRef.current.close()
        } catch (_) {}
        wsRef.current = null
      }

      try {
        const ws = new WebSocket(WS_URL)
        wsRef.current = ws
        if (typeof window !== 'undefined') {
          ;(window as any).__ws = ws
        }

        ws.onopen = () => {
          if (!isMounted) {
            ws.close()
            return
          }
          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current)
            reconnectTimeoutRef.current = null
          }
          setWsConnected(true)
          console.log('[WS] Connected to live trading pipeline')
          // Backfill & resync after connect or reconnect
          fetchCandles(symbolRef.current, timeframeRef.current)
          fetchSignals()
          fetchNews()
          fetchSystemStatus()
        }

        ws.onmessage = (event) => {
          if (!isMounted) return
          try {
            const msg = JSON.parse(event.data)
            handleIncomingWSMessageRef.current(msg)
          } catch (err) {
            console.error('[WS] Parse error:', err)
          }
        }

        ws.onclose = () => {
          if (!isMounted) return
          setWsConnected(false)
          console.log('[WS] Disconnected. Reconnecting in 3 seconds...')
          if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
          reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000)
        }

        ws.onerror = (err) => {
          console.warn('[WS] Error:', err)
          ws.close()
        }
      } catch (e) {
        console.error('[WS] Init failed:', e)
        if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000)
      }
    }

    connectWebSocket()

    return () => {
      isMounted = false
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      if (wsRef.current) {
        try {
          wsRef.current.close()
        } catch (_) {}
        wsRef.current = null
      }
    }
  }, [])

  // 3. Historical Replay Mode Controller
  const handleToggleReplay = async () => {
    if (!isReplayMode) {
      try {
        const res = await fetch(`${API_BASE}/api/replay/candles?symbol=${encodeURIComponent(symbol)}`)
        if (res.ok) {
          const data = await res.json()
          if (data.candles && data.candles.length > 0) {
            setAllReplayCandles(data.candles)
            setReplayIndex(Math.min(50, data.candles.length - 1))
            setCandles(data.candles.slice(0, Math.min(50, data.candles.length)))
            setIsReplayMode(true)
            setIsReplayPlaying(true)
          }
        }
      } catch (err) {
        console.error('Failed to load replay data:', err)
      }
    } else {
      setIsReplayPlaying(false)
      setIsReplayMode(false)
      if (replayIntervalRef.current) clearInterval(replayIntervalRef.current)
      fetchCandles(symbol, timeframe)
    }
  }

  useEffect(() => {
    if (isReplayMode && isReplayPlaying) {
      const intervalMs = Math.max(50, Math.floor(1000 / replaySpeed))
      replayIntervalRef.current = setInterval(() => {
        setReplayIndex((prevIndex) => {
          if (prevIndex >= allReplayCandles.length - 1) {
            setIsReplayPlaying(false)
            return prevIndex
          }
          const nextIndex = prevIndex + 1
          setCandles(allReplayCandles.slice(0, nextIndex + 1))
          return nextIndex
        })
      }, intervalMs)
    } else {
      if (replayIntervalRef.current) clearInterval(replayIntervalRef.current)
    }

    return () => {
      if (replayIntervalRef.current) clearInterval(replayIntervalRef.current)
    }
  }, [isReplayMode, isReplayPlaying, replaySpeed, allReplayCandles])

  const handleScrubReplay = (index: number) => {
    setReplayIndex(index)
    if (allReplayCandles.length > 0) {
      setCandles(allReplayCandles.slice(0, index + 1))
    }
  }

  const handleResetReplay = () => {
    setReplayIndex(Math.min(20, allReplayCandles.length - 1))
    if (allReplayCandles.length > 0) {
      setCandles(allReplayCandles.slice(0, Math.min(20, allReplayCandles.length)))
    }
  }

  const matchedOrder = selectedSignal
    ? paperOrders.find((o) => o.id === selectedSignal.order_id) || null
    : null

  const currentReplayTimeStr =
    isReplayMode && allReplayCandles[replayIndex]
      ? new Date(allReplayCandles[replayIndex].time * 1000).toLocaleString()
      : ''

  return (
    <div className="flex flex-col min-h-screen bg-[#070a10] text-slate-100 font-sans selection:bg-blue-600 selection:text-white">
      {/* Top Header with Asset Class, Symbols, Tabs & Telemetry */}
      <TopBar
        assetType={assetType}
        onChangeAssetType={handleAssetTypeChange}
        selectedSymbol={symbol}
        onSelectSymbol={handleSelectSymbol}
        currentPrice={currentPrice}
        priceChange={priceChange}
        priceChangePercent={priceChangePercent}
        wsConnected={wsConnected}
        isReplayMode={isReplayMode}
        onToggleReplay={handleToggleReplay}
        pipelineStatus={pipelineStatus}
        activeTab={activeTab}
        onChangeTab={setActiveTab}
      />

      {/* Main Terminal Views */}
      <main className="flex-1 p-3 md:p-4 overflow-y-auto">
        <ErrorBoundary fallbackTitle="View Rendering Error">
        {activeTab === 'terminal' && (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-3 md:gap-4 overflow-hidden">
            {/* Left Section: Chart & Panels (3 Columns) */}
            <div className="lg:col-span-3 flex flex-col gap-3 md:gap-4 min-h-0">
              {/* Candlestick & Indicators Chart */}
              <div className="h-[460px] md:h-[520px] w-full">
                <TradingChart
                  candles={candles}
                  signals={signals}
                  symbol={symbol}
                  timeframe={timeframe}
                  onSelectTimeframe={setTimeframe}
                  onSelectSignal={setSelectedSignal}
                />
              </div>

              {/* Historical Replay Playback Bar (when active) */}
              {isReplayMode && (
                <HistoricalReplayBar
                  isPlaying={isReplayPlaying}
                  onTogglePlay={() => setIsReplayPlaying(!isReplayPlaying)}
                  speed={replaySpeed}
                  onChangeSpeed={setReplaySpeed}
                  currentIndex={replayIndex}
                  totalCount={allReplayCandles.length}
                  onScrub={handleScrubReplay}
                  onReset={handleResetReplay}
                  currentTimeStr={currentReplayTimeStr}
                />
              )}

              {/* Bottom Grid: Signal History & News Sentiment */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4 h-[320px]">
                <SignalHistoryPanel
                  signals={signals}
                  onSelectSignal={setSelectedSignal}
                />
                <NewsSentimentPanel
                  news={news}
                  selectedSymbol={symbol}
                />
              </div>
            </div>

            {/* Right Section: Paper Trading & Pipeline Monitor (1 Column) */}
            <div className="flex flex-col gap-3 md:gap-4 h-full">
              {/* Paper Trading Panel */}
              <div className="h-[380px]">
                <PaperTradingPanel
                  account={paperAccount}
                  positions={paperPositions}
                  orders={paperOrders}
                  loading={paperLoading}
                  onRefresh={fetchPaperData}
                />
              </div>

              {/* Pipeline Monitor & Telemetry Panel */}
              <div className="flex-1 min-h-[360px]">
                <PipelineMonitorPanel status={pipelineStatus} />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'analytics' && (
          <div className="max-w-7xl mx-auto">
            <StrategyAnalyticsPanel asset={symbol} />
          </div>
        )}

        {activeTab === 'portfolio' && (
          <div className="max-w-7xl mx-auto">
            <PortfolioPanel apiBase={API_BASE} />
          </div>
        )}

        {activeTab === 'paper_bot' && (
          <div className="max-w-7xl mx-auto">
            <PaperBotPanel apiBase={API_BASE} />
          </div>
        )}

        {activeTab === 'backtesting' && (
          <div className="max-w-7xl mx-auto">
            <BacktestPanel apiBase={API_BASE} />
          </div>
        )}

        {activeTab === 'workbench' && (
          <div className="max-w-7xl mx-auto">
            <TradingWorkbenchPanel apiBase={API_BASE} />
          </div>
        )}

        {activeTab === 'observability' && (
          <div className="max-w-7xl mx-auto">
            <StreamingObservabilityPanel />
          </div>
        )}

        {activeTab === 'reliability' && (
          <div className="max-w-7xl mx-auto">
            <ReliabilityLogsPanel />
          </div>
        )}
        </ErrorBoundary>
      </main>

      {/* Deep-dive Signal Inspection Modal */}
      {selectedSignal && (
        <SignalModal
          signal={selectedSignal}
          matchedOrder={matchedOrder}
          onClose={() => setSelectedSignal(null)}
        />
      )}
    </div>
  )
}

export default App
