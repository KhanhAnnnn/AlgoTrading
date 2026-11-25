import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import type {
  V2BacktestRun,
  BacktestChartBundle,
  BacktestSimulatedFill,
  BacktestClosedTrade,
} from '../types'
import { BacktestTradeChart } from './BacktestTradeChart'
import type { ChartFocusRequest } from './BacktestTradeChart'
import {
  Play,
  RotateCcw,
  Shield,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Database,
  List,
  Fingerprint,
  Download,
  Sparkles,
  RefreshCw,
  CandlestickChart,
  Filter,
  Search,
  ArrowUpRight,
  ArrowDownRight,
  BookOpen,
} from 'lucide-react'

interface BacktestPanelProps {
  apiBase?: string
}

type BacktestStage = 'IDLE' | 'FETCHING' | 'VALIDATING' | 'CACHING' | 'BACKTESTING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'

export const BacktestPanel: React.FC<BacktestPanelProps> = ({
  apiBase = 'http://127.0.0.1:8005'
}) => {
  // State
  const [runs, setRuns] = useState<V2BacktestRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string>('')
  const [selectedRun, setSelectedRun] = useState<V2BacktestRun | null>(null)
  const [trades, setTrades] = useState<any[]>([])
  const [equityCurve, setEquityCurve] = useState<any[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [actionLoading, setActionLoading] = useState<boolean>(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'chart' | 'metrics' | 'trades' | 'equity' | 'experiments' | 'provenance'>('chart')
  const [experiments, setExperiments] = useState<any[]>([])
  const [selectedExpId, setSelectedExpId] = useState<string>('')
  const [comparisonData, setComparisonData] = useState<any>(null)

  // GĐ41 Interactive Trade Chart & Explorer State
  const [chartBundle, setChartBundle] = useState<BacktestChartBundle | null>(null)
  const [chartLoading, setChartLoading] = useState<boolean>(false)
  const [chartSymbol, setChartSymbol] = useState<string>('')
  const [selectedFillId, setSelectedFillId] = useState<string | null>(null)
  const [focusRequest, setFocusRequest] = useState<ChartFocusRequest | null>(null)
  const [explorerView, setExplorerView] = useState<'fills' | 'closed_trades' | 'ledger'>('fills')
  const [filterSide, setFilterSide] = useState<'ALL' | 'BUY' | 'SELL'>('ALL')
  const [filterOutcome, setFilterOutcome] = useState<'ALL' | 'WIN' | 'LOSS'>('ALL')
  const [filterSymbol, setFilterSymbol] = useState<string>('ALL')
  const [filterStrategy, setFilterStrategy] = useState<string>('ALL')
  const [filterSearch, setFilterSearch] = useState<string>('')
  const fillRowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const focusNonceRef = useRef<number>(1)

  const [supportedStocks, setSupportedStocks] = useState<Array<{ symbol: string; name: string }>>([
    { symbol: 'NVDA', name: 'NVIDIA Corp' },
    { symbol: 'AAPL', name: 'Apple Inc' },
    { symbol: 'TSLA', name: 'Tesla Inc' },
    { symbol: 'MSFT', name: 'Microsoft Corp' },
  ])
  const [supportedCrypto, setSupportedCrypto] = useState<Array<{ symbol: string; name: string }>>([
    { symbol: 'BTC/USD', name: 'Bitcoin' },
    { symbol: 'ETH/USD', name: 'Ethereum' },
    { symbol: 'SOL/USD', name: 'Solana' },
  ])

  // Strategy Parameter Overrides
  const [fastPeriod, setFastPeriod] = useState<number>(20)
  const [slowPeriod, setSlowPeriod] = useState<number>(50)
  const [rsiPeriod, setRsiPeriod] = useState<number>(14)
  const [rsiOversold, setRsiOversold] = useState<number>(30)
  const [rsiOverbought, setRsiOverbought] = useState<number>(70)

  // GĐ41: Market Data & Provenance Controls
  const [dataSource, setDataSource] = useState<'ALPACA_LIVE' | 'LOCAL_CACHE' | 'SYNTHETIC'>('ALPACA_LIVE')
  const [assetClass, setAssetClass] = useState<'STOCKS' | 'CRYPTO'>('STOCKS')
  const [symbol, setSymbol] = useState<string>('NVDA')
  const [timeframe, setTimeframe] = useState<string>('1m')
  const [feed, setFeed] = useState<'IEX' | 'SIP'>('IEX')
  const [startDate, setStartDate] = useState<string>('2024-11-20T14:30')
  const [endDate, setEndDate] = useState<string>('2024-11-20T16:30')
  const [forceRefresh, setForceRefresh] = useState<boolean>(false)
  const [availableDatasets, setAvailableDatasets] = useState<any[]>([])
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('')

  // Multi-step Execution Stage Tracker
  const [executionStage, setExecutionStage] = useState<BacktestStage>('IDLE')
  const [stageMessage, setStageMessage] = useState<string>('')

  // Form Strategy & Simulation State
  const [strategyId, setStrategyId] = useState<string>('MA_CROSS_1M')
  const [marketSessionPolicy, setMarketSessionPolicy] = useState<'STRICT_HOURS' | 'ALL_HOURS'>('STRICT_HOURS')
  const [initialCapital, setInitialCapital] = useState<number>(100000)
  const [warmupBars, setWarmupBars] = useState<number>(20)
  const [feeModel, setFeeModel] = useState<string>('DEFAULT')
  const [slippageModel, setSlippageModel] = useState<string>('DEFAULT')

  // Auto-detect asset class when symbol changes
  const handleSymbolChange = (newSym: string) => {
    setSymbol(newSym)
    if (newSym.includes('/') || newSym.includes('-') || newSym === 'BTC' || newSym === 'ETH') {
      setAssetClass('CRYPTO')
    } else {
      setAssetClass('STOCKS')
    }
  }

  // Quick preset helper (values treated explicitly as UTC)
  const applyDatePreset = (preset: '2H_SESSION' | 'FULL_DAY' | 'CRYPTO_24H' | 'CRYPTO_3D') => {
    if (preset === '2H_SESSION') {
      setStartDate('2024-11-20T14:30')
      setEndDate('2024-11-20T16:30')
    } else if (preset === 'FULL_DAY') {
      setStartDate('2024-11-20T14:30')
      setEndDate('2024-11-20T21:00')
    } else if (preset === 'CRYPTO_24H') {
      setAssetClass('CRYPTO')
      if (!symbol.includes('/')) setSymbol('BTC/USD')
      setStartDate('2024-11-20T00:00')
      setEndDate('2024-11-20T23:59')
    } else if (preset === 'CRYPTO_3D') {
      setAssetClass('CRYPTO')
      if (!symbol.includes('/')) setSymbol('BTC/USD')
      setStartDate('2024-11-18T00:00')
      setEndDate('2024-11-21T00:00')
    }
  }

  const toUtcIso = (dtLocal: string): string => {
    if (!dtLocal) return new Date().toISOString()
    if (dtLocal.endsWith('Z') || dtLocal.includes('+')) return dtLocal
    return dtLocal.length === 16 ? `${dtLocal}:00Z` : `${dtLocal}Z`
  }

  // Fetch runs list
  const fetchRuns = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/v2/backtests`, {
        headers: { 'X-API-KEY': 'simulation_token_v2' }
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setRuns(data)
      if (data.length > 0 && !selectedRunId) {
        setSelectedRunId(data[0].run_id)
      }
    } catch (err: any) {
      setErrorMsg(`Failed to load backtests: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }, [apiBase, selectedRunId])

  // Fetch cached datasets
  const fetchDatasets = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/v2/historical-data/datasets`, {
        headers: { 'X-API-KEY': 'simulation_token_v2' }
      })
      if (res.ok) {
        const data = await res.json()
        setAvailableDatasets(data)
        if (data.length > 0 && !selectedDatasetId) {
          setSelectedDatasetId(data[0].dataset_id)
        }
      }
    } catch (err) {
      console.error('Failed to load datasets:', err)
    }
  }, [apiBase, selectedDatasetId])

  useEffect(() => {
    fetchRuns()
    fetchDatasets()
    fetch(`${apiBase}/api/v2/historical-data/symbols`, {
      headers: { 'X-API-KEY': 'simulation_token_v2' },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.stocks?.length) setSupportedStocks(data.stocks)
        if (data?.crypto?.length) setSupportedCrypto(data.crypto)
      })
      .catch(() => {})
  }, [fetchRuns, fetchDatasets, apiBase])

  // Fetch run details & chart bundle when selected
  useEffect(() => {
    if (!selectedRunId) return

    const loadRunDetails = async () => {
      setChartLoading(true)
      try {
        const [resRes, tradesRes, equityRes, chartRes] = await Promise.all([
          fetch(`${apiBase}/api/v2/backtests/${selectedRunId}/results`, {
            headers: { 'X-API-KEY': 'simulation_token_v2' }
          }),
          fetch(`${apiBase}/api/v2/backtests/${selectedRunId}/trades`, {
            headers: { 'X-API-KEY': 'simulation_token_v2' }
          }),
          fetch(`${apiBase}/api/v2/backtests/${selectedRunId}/equity`, {
            headers: { 'X-API-KEY': 'simulation_token_v2' }
          }),
          fetch(`${apiBase}/api/v2/backtests/${selectedRunId}/chart`, {
            headers: { 'X-API-KEY': 'simulation_token_v2' }
          }),
        ])

        if (resRes.ok) {
          const resData = await resRes.json()
          setSelectedRun(resData)
        }
        if (tradesRes.ok) {
          const tradesData = await tradesRes.json()
          setTrades(tradesData)
        }
        if (equityRes.ok) {
          const equityData = await equityRes.json()
          setEquityCurve(equityData)
        }
        if (chartRes.ok) {
          const chartData: BacktestChartBundle = await chartRes.json()
          setChartBundle(chartData)
          const defaultSym = chartData.symbols?.[0] || chartData.candles?.[0]?.symbol || 'NVDA'
          setChartSymbol(defaultSym)
          setSelectedFillId(null)
          setFocusRequest(null)
        } else {
          setChartBundle(null)
        }
      } catch (err: any) {
        console.error('Failed to load run details:', err)
      } finally {
        setChartLoading(false)
      }
    }

    loadRunDetails()
  }, [apiBase, selectedRunId])

  // Experiments
  const fetchExperiments = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/v2/experiments`, {
        headers: { 'X-API-KEY': 'simulation_token_v2' }
      })
      if (res.ok) {
        const data = await res.json()
        const exps = data.experiments || []
        setExperiments(exps)
        if (exps.length > 0 && !selectedExpId) {
          setSelectedExpId(exps[0].experiment_id)
        }
      }
    } catch (e) {
      console.error('Failed to load experiments', e)
    }
  }, [apiBase, selectedExpId])

  useEffect(() => {
    if (activeTab === 'experiments') {
      fetchExperiments()
    }
  }, [activeTab, fetchExperiments])

  useEffect(() => {
    if (selectedExpId) {
      fetch(`${apiBase}/api/v2/experiments/${selectedExpId}/comparison`, {
        headers: { 'X-API-KEY': 'simulation_token_v2' }
      })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => setComparisonData(data))
        .catch((e) => console.error('Failed to load comparison', e))
    }
  }, [apiBase, selectedExpId])

  // Handle run launch (GĐ41 One-Click Integration)
  const handleLaunchBacktest = async (e: React.FormEvent) => {
    e.preventDefault()
    setActionLoading(true)
    setErrorMsg(null)
    setExecutionStage('FETCHING')
    setStageMessage('Connecting to Alpaca Market Data API...')

    const strategyParamsPayload = strategyId.includes('RSI')
      ? {
          period: Number(rsiPeriod),
          oversold: Number(rsiOversold),
          overbought: Number(rsiOverbought),
          fast_period: Number(fastPeriod),
          slow_period: Number(slowPeriod),
        }
      : {
          fast_period: Number(fastPeriod),
          slow_period: Number(slowPeriod),
          period: Number(rsiPeriod),
          oversold: Number(rsiOversold),
          overbought: Number(rsiOverbought),
        }

    try {
      let createdRun: any = null

      if (dataSource === 'ALPACA_LIVE') {
        // Stage 1: Fetching
        setExecutionStage('FETCHING')
        setStageMessage(`Fetching 1m bars for ${symbol} from Alpaca (${assetClass === 'STOCKS' ? feed : 'CRYPTO'})...`)

        const sIso = toUtcIso(startDate)
        const eIso = toUtcIso(endDate)

        const payload = {
          symbol: symbol.toUpperCase(),
          asset_class: assetClass,
          timeframe: timeframe,
          start_time: sIso,
          end_time: eIso,
          feed: feed,
          force_refresh: forceRefresh,
          strategy_id: strategyId,
          strategy_version: '1.0.0',
          initial_simulated_cash: Number(initialCapital),
          warmup_bars_count: Number(warmupBars),
          market_session_policy: assetClass === 'CRYPTO' ? 'ALL_HOURS' : marketSessionPolicy,
          fee_model: feeModel,
          slippage_model: slippageModel,
          execution_config: { strategy_params: strategyParamsPayload },
        }

        setExecutionStage('VALIDATING')
        setStageMessage('Validating OHLCV mathematical integrity & session calendar...')

        setExecutionStage('CACHING')
        setStageMessage('Hashing dataset manifest (SHA-256) & persisting local cache...')

        setExecutionStage('BACKTESTING')
        setStageMessage('Simulating next-eligible-bar execution & order matching...')

        const res = await fetch(`${apiBase}/api/v2/backtests/from-alpaca`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-KEY': 'simulation_token_v2',
          },
          body: JSON.stringify(payload),
        })

        if (!res.ok) {
          const errJson = await res.json().catch(() => ({}))
          throw new Error(errJson.detail || `HTTP ${res.status}`)
        }

        createdRun = await res.json()
        setExecutionStage('COMPLETED')
        setStageMessage(`Backtest complete! Replayed ${createdRun.dataset?.total_bars || 0} real bars.`)

      } else if (dataSource === 'LOCAL_CACHE') {
        if (!selectedDatasetId) {
          throw new Error('Please select a cached dataset from the dropdown.')
        }
        setExecutionStage('BACKTESTING')
        setStageMessage(`Replaying cached dataset '${selectedDatasetId}'...`)

        const dsObj = availableDatasets.find((d: any) => d.dataset_id === selectedDatasetId)
        const dsIsCrypto = dsObj?.asset_class === 'CRYPTO' || (dsObj?.symbols || []).some((s: string) => s.includes('/'))
        const payload = {
          dataset_id: selectedDatasetId,
          strategy_id: strategyId,
          strategy_version: '1.0.0',
          initial_simulated_cash: Number(initialCapital),
          warmup_bars_count: Number(warmupBars),
          market_session_policy: dsIsCrypto ? 'ALL_HOURS' : marketSessionPolicy,
          fee_model: feeModel,
          slippage_model: slippageModel,
          execution_config: { strategy_params: strategyParamsPayload },
        }

        const res = await fetch(`${apiBase}/api/v2/backtests/from-dataset`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-KEY': 'simulation_token_v2',
          },
          body: JSON.stringify(payload),
        })

        if (!res.ok) {
          const errJson = await res.json().catch(() => ({}))
          throw new Error(errJson.detail || `HTTP ${res.status}`)
        }

        createdRun = await res.json()
        setExecutionStage('COMPLETED')
        setStageMessage(`Backtest completed on cached dataset '${selectedDatasetId}'`)

      } else {
        // SYNTHETIC FIXTURE
        setExecutionStage('BACKTESTING')
        setStageMessage('Running synthetic fixture simulation...')

        const payload = {
          strategy_id: strategyId,
          symbols: [symbol],
          initial_simulated_cash: Number(initialCapital),
          warmup_bars_count: Number(warmupBars),
          fee_model: feeModel,
          slippage_model: slippageModel,
          synthetic_bars_count: 150,
          execution_config: { strategy_params: strategyParamsPayload },
        }

        const res = await fetch(`${apiBase}/api/v2/backtests`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-KEY': 'simulation_token_v2',
          },
          body: JSON.stringify(payload),
        })

        if (!res.ok) {
          const errJson = await res.json().catch(() => ({}))
          throw new Error(errJson.detail || `HTTP ${res.status}`)
        }

        createdRun = await res.json()
        setExecutionStage('COMPLETED')
        setStageMessage('Synthetic fixture test complete.')
      }

      await fetchRuns()
      await fetchDatasets()
      if (createdRun?.run_id) {
        setSelectedRunId(createdRun.run_id)
      }
    } catch (err: any) {
      setExecutionStage('FAILED')
      setStageMessage(`Failed: ${err.message}`)
      setErrorMsg(`Backtest error: ${err.message}`)
    } finally {
      setActionLoading(false)
    }
  }

  const metrics = selectedRun?.metrics
  const runDataset = selectedRun?.dataset
  const isRealData = runDataset && !runDataset.is_synthetic

  // Bidirectional Trade Explorer derived maps & filters
  const linkedTradeByFillId = useMemo(() => {
    const m = new Map<string, BacktestClosedTrade>()
    ;(chartBundle?.closed_trades || []).forEach((t) => {
      m.set(t.exit_fill_id, t)
      t.entry_fill_ids.forEach((id) => m.set(id, t))
    })
    return m
  }, [chartBundle])

  const availableFilterSymbols = useMemo(() => {
    const s = new Set<string>()
    ;(chartBundle?.fills || trades || []).forEach((f: any) => s.add(f.symbol))
    return Array.from(s)
  }, [chartBundle, trades])

  const availableFilterStrategies = useMemo(() => {
    const s = new Set<string>()
    if (selectedRun?.config?.strategy_id) s.add(selectedRun.config.strategy_id)
    ;(chartBundle?.fills || []).forEach((f) => {
      if (f.strategy_id) s.add(f.strategy_id)
    })
    return Array.from(s)
  }, [chartBundle, selectedRun])

  const filteredFills: BacktestSimulatedFill[] = useMemo(() => {
    const raw: BacktestSimulatedFill[] = chartBundle?.fills || (trades as BacktestSimulatedFill[]) || []
    const q = filterSearch.trim().toLowerCase()
    return raw.filter((f) => {
      if (filterSide !== 'ALL' && f.side.toUpperCase() !== filterSide) return false
      if (filterSymbol !== 'ALL' && f.symbol !== filterSymbol) return false
      if (filterStrategy !== 'ALL' && (f.strategy_id || selectedRun?.config?.strategy_id) !== filterStrategy) return false
      if (filterOutcome !== 'ALL') {
        const linked = linkedTradeByFillId.get(f.simulated_fill_id)
        if (!linked) return false
        if (filterOutcome === 'WIN' && !linked.is_win) return false
        if (filterOutcome === 'LOSS' && linked.is_win) return false
      }
      if (q) {
        const hay = `${f.simulated_fill_id} ${f.simulated_order_id} ${f.symbol} ${f.strategy_reason || ''}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  }, [chartBundle, trades, filterSide, filterSymbol, filterStrategy, filterOutcome, filterSearch, linkedTradeByFillId, selectedRun])

  const filteredClosedTrades: BacktestClosedTrade[] = useMemo(() => {
    const raw = chartBundle?.closed_trades || []
    const q = filterSearch.trim().toLowerCase()
    return raw.filter((t) => {
      if (filterSymbol !== 'ALL' && t.symbol !== filterSymbol) return false
      if (filterStrategy !== 'ALL' && (t.strategy_id || selectedRun?.config?.strategy_id) !== filterStrategy) return false
      if (filterOutcome === 'WIN' && !t.is_win) return false
      if (filterOutcome === 'LOSS' && t.is_win) return false
      if (q) {
        const hay = `${t.trade_id} ${t.exit_fill_id} ${t.entry_fill_ids.join(' ')} ${t.entry_reason || ''} ${t.exit_reason || ''}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  }, [chartBundle, filterSymbol, filterStrategy, filterOutcome, filterSearch, selectedRun])

  const handleSelectFillFromChart = useCallback((fill: BacktestSimulatedFill) => {
    setSelectedFillId(fill.simulated_fill_id)
    setExplorerView('fills')
    const row = fillRowRefs.current[fill.simulated_fill_id]
    if (row) {
      row.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [])

  const handleZoomToFill = (fill: BacktestSimulatedFill) => {
    setSelectedFillId(fill.simulated_fill_id)
    if (fill.symbol && fill.symbol !== chartSymbol) {
      setChartSymbol(fill.symbol)
    }
    const ep = fill.fill_epoch ?? Math.floor(new Date(fill.fill_time).getTime() / 1000)
    focusNonceRef.current += 1
    setFocusRequest({ epoch: ep, fillId: fill.simulated_fill_id, nonce: focusNonceRef.current })
    setActiveTab('chart')
  }

  const handleZoomToClosedTrade = (trade: BacktestClosedTrade) => {
    setSelectedFillId(trade.exit_fill_id)
    if (trade.symbol && trade.symbol !== chartSymbol) {
      setChartSymbol(trade.symbol)
    }
    focusNonceRef.current += 1
    setFocusRequest({
      epoch: trade.entry_epoch,
      endEpoch: trade.exit_epoch,
      tradeId: trade.trade_id,
      nonce: focusNonceRef.current,
    })
    setActiveTab('chart')
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 text-slate-100 p-6 overflow-y-auto">
      {/* Top Banner */}
      <div className="flex items-center justify-between pb-6 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <Database className="w-7 h-7 text-indigo-400" />
              Historical Backtesting & Strategy Replay Engine
            </h1>
            <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
              AlgoTrading V2.0 (GĐ41)
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Real Alpaca 1-minute historical data • Local cache persistence • Provenance auditing • Zero look-ahead bias
          </p>
        </div>

        {/* Safety Badges */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-900 border border-slate-800 text-xs">
            <Shield className="w-4 h-4 text-emerald-400" />
            <span className="text-slate-400">Trading Mode:</span>
            <span className="font-semibold text-emerald-400">DRY_RUN</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-900 border border-slate-800 text-xs">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="text-slate-400">Execution Gate:</span>
            <span className="font-semibold text-emerald-400">CLOSED (SAFE)</span>
          </div>
        </div>
      </div>

      {/* Progress & Stage Status Banner */}
      {executionStage !== 'IDLE' && (
        <div className={`mt-4 p-3.5 rounded-xl border text-xs flex items-center justify-between transition-all ${
          executionStage === 'COMPLETED'
            ? 'bg-emerald-950/60 border-emerald-800/80 text-emerald-200'
            : executionStage === 'FAILED'
            ? 'bg-rose-950/60 border-rose-800/80 text-rose-200'
            : 'bg-indigo-950/60 border-indigo-800/80 text-indigo-200'
        }`}>
          <div className="flex items-center gap-3">
            <span className={`px-2 py-0.5 rounded font-mono font-bold text-[10px] tracking-wider uppercase ${
              executionStage === 'COMPLETED' ? 'bg-emerald-800 text-white' :
              executionStage === 'FAILED' ? 'bg-rose-800 text-white' :
              'bg-indigo-700 text-white animate-pulse'
            }`}>
              {executionStage}
            </span>
            <span className="font-medium">{stageMessage}</span>
          </div>
          {executionStage !== 'COMPLETED' && executionStage !== 'FAILED' && (
            <RotateCcw className="w-4 h-4 animate-spin text-indigo-400" />
          )}
        </div>
      )}

      {errorMsg && executionStage !== 'FAILED' && (
        <div className="mt-4 p-3 rounded-lg bg-red-950/80 border border-red-800 text-red-300 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-12 gap-6 mt-6 flex-1">
        {/* Left Column: Form & History List */}
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
          {/* Launch Config Form */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-sm">
            <h2 className="text-base font-semibold text-white flex items-center gap-2 mb-4">
              <Play className="w-4 h-4 text-indigo-400" />
              Configure & Run Backtest
            </h2>

            <form onSubmit={handleLaunchBacktest} className="space-y-4 text-sm">
              {/* 1. Market Data Source Selector */}
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1 flex items-center justify-between">
                  <span>Market Data Source</span>
                  <span className="text-[10px] text-indigo-400">GĐ41 Integrated</span>
                </label>
                <select
                  value={dataSource}
                  onChange={(e: any) => setDataSource(e.target.value)}
                  className="w-full bg-slate-950 border border-indigo-700/60 rounded-lg px-3 py-2 text-white text-xs focus:ring-1 focus:ring-indigo-500 font-medium"
                >
                  <option value="ALPACA_LIVE">Alpaca Historical API (Live Real-Data Fetch)</option>
                  <option value="LOCAL_CACHE">Verified Local Cache (Instant Replay)</option>
                  <option value="SYNTHETIC">Synthetic Fixture (Testing & Demos Only)</option>
                </select>
              </div>

              {/* Conditional local cache picker */}
              {dataSource === 'LOCAL_CACHE' && (
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Select Cached Dataset</label>
                  <select
                    value={selectedDatasetId}
                    onChange={(e) => setSelectedDatasetId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs font-mono"
                  >
                    {availableDatasets.length === 0 ? (
                      <option value="">No local datasets found. Use Alpaca Live first.</option>
                    ) : (
                      availableDatasets.map((ds: any) => (
                        <option key={ds.dataset_id} value={ds.dataset_id}>
                          {ds.dataset_id} ({ds.total_bars} bars, {ds.symbols?.join(', ')} - {ds.feed})
                        </option>
                      ))
                    )}
                  </select>
                </div>
              )}

              {/* Asset Class & Symbol Controls */}
              {dataSource !== 'LOCAL_CACHE' && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1">Asset Class</label>
                      <select
                        value={assetClass}
                        onChange={(e: any) => {
                          const ac = e.target.value
                          setAssetClass(ac)
                          if (ac === 'CRYPTO' && !symbol.includes('/')) {
                            setSymbol('BTC/USD')
                          } else if (ac === 'STOCKS' && symbol.includes('/')) {
                            setSymbol('NVDA')
                          }
                        }}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs"
                      >
                        <option value="STOCKS">US Equities (Stocks)</option>
                        <option value="CRYPTO">Crypto 24/7 (Alpaca)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1">Symbol</label>
                      {assetClass === 'STOCKS' ? (
                        <select
                          value={symbol}
                          onChange={(e) => handleSymbolChange(e.target.value)}
                          className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs font-semibold"
                        >
                          {supportedStocks.map((item) => (
                            <option key={item.symbol} value={item.symbol}>
                              {item.symbol} ({item.name})
                            </option>
                          ))}
                        </select>
                      ) : (
                        <select
                          value={symbol}
                          onChange={(e) => handleSymbolChange(e.target.value)}
                          className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs font-semibold"
                        >
                          {supportedCrypto.map((item) => (
                            <option key={item.symbol} value={item.symbol}>
                              {item.symbol} ({item.name})
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  </div>

                  {/* Stock Feed & Timeframe */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1">Stock Feed</label>
                      <select
                        value={feed}
                        disabled={assetClass === 'CRYPTO'}
                        onChange={(e: any) => setFeed(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs disabled:opacity-50"
                      >
                        <option value="IEX">IEX (Investors Exchange - Free)</option>
                        <option value="SIP">SIP (Full Market Data Feed)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1">Timeframe</label>
                      <input
                        type="text"
                        value={`${timeframe} (1-Minute OHLCV)`}
                        onChange={(e) => setTimeframe(e.target.value)}
                        disabled
                        className="w-full bg-slate-950/60 border border-slate-800 rounded-lg px-3 py-2 text-slate-400 text-xs font-mono"
                      />
                    </div>
                  </div>

                  {/* Historical Date Pickers */}
                  <div className="space-y-2 pt-1 border-t border-slate-800/80">
                    <div className="flex items-center justify-between">
                      <label className="block text-xs font-medium text-slate-400">Date Range (Historical UTC)</label>
                      <div className="flex flex-wrap items-center gap-1 text-[10px]">
                        <button
                          type="button"
                          onClick={() => applyDatePreset('2H_SESSION')}
                          className="px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
                        >
                          2h US
                        </button>
                        <button
                          type="button"
                          onClick={() => applyDatePreset('FULL_DAY')}
                          className="px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
                        >
                          1d US
                        </button>
                        <button
                          type="button"
                          onClick={() => applyDatePreset('CRYPTO_24H')}
                          className="px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
                        >
                          Crypto 24h
                        </button>
                        <button
                          type="button"
                          onClick={() => applyDatePreset('CRYPTO_3D')}
                          className="px-1.5 py-0.5 rounded bg-indigo-900/70 hover:bg-indigo-800 text-indigo-200 border border-indigo-700/60"
                        >
                          Crypto 3d
                        </button>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <span className="text-[10px] text-slate-500">Start (UTC)</span>
                        <input
                          type="datetime-local"
                          value={startDate}
                          onChange={(e) => setStartDate(e.target.value)}
                          className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-white text-xs font-mono"
                        />
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-500">End (UTC)</span>
                        <input
                          type="datetime-local"
                          value={endDate}
                          onChange={(e) => setEndDate(e.target.value)}
                          className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-white text-xs font-mono"
                        />
                      </div>
                    </div>

                    <div className="flex items-center gap-2 pt-1">
                      <input
                        type="checkbox"
                        id="forceRefreshChk"
                        checked={forceRefresh}
                        onChange={(e) => setForceRefresh(e.target.checked)}
                        className="rounded border-slate-800 text-indigo-600 focus:ring-0"
                      />
                      <label htmlFor="forceRefreshChk" className="text-[11px] text-slate-400 cursor-pointer">
                        Force refresh from Alpaca API (bypass local cache)
                      </label>
                    </div>
                  </div>
                </>
              )}

              {/* Strategy & Capital Controls */}
              <div className="pt-2 border-t border-slate-800/80 space-y-3">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Strategy Preset</label>
                  <select
                    value={strategyId}
                    onChange={(e) => setStrategyId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs"
                  >
                    <option value="MA_CROSS_1M">MA Crossover (SMA Fast/Slow 1m)</option>
                    <option value="RSI_1M">RSI Mean Reversion (1m)</option>
                  </select>
                </div>

                {/* Indicator Parameters */}
                {strategyId.includes('RSI') ? (
                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <span className="text-[10px] text-slate-500">RSI Period</span>
                      <input
                        type="number"
                        min={2}
                        value={rsiPeriod}
                        onChange={(e) => setRsiPeriod(Number(e.target.value))}
                        className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-white text-xs font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500">Oversold</span>
                      <input
                        type="number"
                        min={1}
                        max={49}
                        value={rsiOversold}
                        onChange={(e) => setRsiOversold(Number(e.target.value))}
                        className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-white text-xs font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500">Overbought</span>
                      <input
                        type="number"
                        min={51}
                        max={99}
                        value={rsiOverbought}
                        onChange={(e) => setRsiOverbought(Number(e.target.value))}
                        className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-white text-xs font-mono"
                      />
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <span className="text-[10px] text-slate-500">MA Fast Period</span>
                      <input
                        type="number"
                        min={2}
                        value={fastPeriod}
                        onChange={(e) => setFastPeriod(Number(e.target.value))}
                        className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-white text-xs font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500">MA Slow Period</span>
                      <input
                        type="number"
                        min={3}
                        value={slowPeriod}
                        onChange={(e) => setSlowPeriod(Number(e.target.value))}
                        className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-white text-xs font-mono"
                      />
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Simulated Capital ($)</label>
                    <input
                      type="number"
                      value={initialCapital}
                      onChange={(e) => setInitialCapital(Number(e.target.value))}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Warmup Bars</label>
                    <input
                      type="number"
                      value={warmupBars}
                      onChange={(e) => setWarmupBars(Number(e.target.value))}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs font-mono"
                    />
                    {!strategyId.includes('RSI') && warmupBars < slowPeriod && (
                      <div className="mt-1 text-[10px] text-amber-300/90 leading-tight">
                        Exec warmup {warmupBars}; MA({slowPeriod}) activates at bar {slowPeriod}.
                      </div>
                    )}
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1 flex items-center justify-between">
                    <span>Market Session Policy</span>
                    <span className="text-[10px] text-slate-500">America/New_York</span>
                  </label>
                  <select
                    value={marketSessionPolicy}
                    onChange={(e: any) => setMarketSessionPolicy(e.target.value)}
                    disabled={assetClass === 'CRYPTO' && dataSource !== 'LOCAL_CACHE'}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs disabled:opacity-60"
                  >
                    <option value="STRICT_HOURS">Regular Trading Hours Only (09:30–16:00 ET)</option>
                    <option value="ALL_HOURS">All Hours (Include Pre-Market & After-Hours)</option>
                  </select>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Fee Model</label>
                    <select
                      value={feeModel}
                      onChange={(e) => setFeeModel(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs"
                    >
                      <option value="DEFAULT">Default (5 bps)</option>
                      <option value="ZERO">Zero Fees</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">Slippage Model</label>
                    <select
                      value={slippageModel}
                      onChange={(e) => setSlippageModel(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs"
                    >
                      <option value="DEFAULT">Fixed (5 bps)</option>
                      <option value="ZERO">Zero Slippage</option>
                      <option value="IMPACT">Volume Impact</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={actionLoading}
                className={`w-full mt-2 py-3 px-4 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition shadow-lg ${
                  dataSource === 'ALPACA_LIVE'
                    ? 'bg-gradient-to-r from-indigo-600 to-emerald-600 hover:from-indigo-500 hover:to-emerald-500 text-white'
                    : dataSource === 'LOCAL_CACHE'
                    ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
                    : 'bg-indigo-600 hover:bg-indigo-500 text-white'
                } disabled:opacity-50`}
              >
                {actionLoading ? (
                  <>
                    <RotateCcw className="w-4 h-4 animate-spin" />
                    Executing Simulation...
                  </>
                ) : dataSource === 'ALPACA_LIVE' ? (
                  <>
                    <Sparkles className="w-4 h-4" />
                    Fetch from Alpaca & Backtest
                  </>
                ) : dataSource === 'LOCAL_CACHE' ? (
                  <>
                    <Database className="w-4 h-4" />
                    Run Backtest from Local Cache
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-white" />
                    Run Synthetic Fixture Test
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Previous Backtest Runs */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-sm flex-1 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                <List className="w-4 h-4 text-indigo-400" />
                Completed Runs ({runs.length})
              </h2>
              <button
                onClick={fetchRuns}
                className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white"
                title="Refresh runs"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-2 max-h-[340px] pr-1">
              {loading ? (
                <div className="text-center py-6 text-slate-500 text-xs">Loading runs...</div>
              ) : runs.length === 0 ? (
                <div className="text-center py-6 text-slate-500 text-xs">No backtests run yet.</div>
              ) : (
                runs.map((r) => {
                  const isSelected = r.run_id === selectedRunId
                  const ret = r.metrics?.net_return_pct ?? 0
                  const isRunReal = r.dataset && !r.dataset.is_synthetic
                  return (
                    <div
                      key={r.run_id}
                      onClick={() => setSelectedRunId(r.run_id)}
                      className={`p-3 rounded-lg border cursor-pointer transition text-xs ${
                        isSelected
                          ? 'bg-indigo-950/40 border-indigo-500/50 text-white'
                          : 'bg-slate-950/60 border-slate-800 text-slate-300 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between font-mono font-medium">
                        <div className="flex items-center gap-1.5">
                          <span>{r.run_id}</span>
                          {isRunReal ? (
                            <span className="px-1.5 py-0.2 rounded text-[9px] bg-emerald-950 text-emerald-400 border border-emerald-800">
                              ALPACA
                            </span>
                          ) : (
                            <span className="px-1.5 py-0.2 rounded text-[9px] bg-amber-950 text-amber-400 border border-amber-800">
                              FIXTURE
                            </span>
                          )}
                        </div>
                        <span className={ret >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                          {ret >= 0 ? '+' : ''}{ret.toFixed(2)}%
                        </span>
                      </div>
                      <div className="flex items-center justify-between mt-1 text-[11px] text-slate-400">
                        <span>{r.config?.strategy_id} • {r.config?.symbols?.join(', ')}</span>
                        <span>{r.metrics?.total_trades ?? 0} trades</span>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Quantitative Analytics & Detail */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">
          {selectedRun && metrics ? (
            <>
              {/* Provenance Strip Banner */}
              <div className={`border rounded-xl p-4 flex flex-wrap items-center justify-between gap-4 ${
                isRealData
                  ? 'bg-emerald-950/20 border-emerald-800/60'
                  : 'bg-amber-950/20 border-amber-800/60'
              }`}>
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-lg border flex items-center justify-center ${
                    isRealData
                      ? 'bg-emerald-950/80 border-emerald-700 text-emerald-400'
                      : 'bg-amber-950/80 border-amber-700 text-amber-400'
                  }`}>
                    <Database className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase ${
                        isRealData
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                          : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                      }`}>
                        {isRealData ? 'REAL ALPACA HISTORICAL DATA' : 'SYNTHETIC FIXTURE (TESTING ONLY)'}
                      </span>
                      {runDataset?.feed && (
                        <span className="text-[11px] font-mono text-slate-300">
                          Feed: <strong className="text-white">{runDataset.feed}</strong>
                        </span>
                      )}
                      {runDataset?.total_bars && (
                        <span className="text-[11px] font-mono text-slate-300">
                          Bars: <strong className="text-white">{runDataset.total_bars}</strong>
                        </span>
                      )}
                    </div>
                    <div className="font-mono text-xs text-slate-300 mt-1 flex items-center gap-2">
                      <span>SHA-256:</span>
                      <span className="text-indigo-300 font-bold select-all">
                        {runDataset?.checksum_sha256 || 'N/A'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {runDataset?.dataset_id && (
                    <a
                      href={`${apiBase}/api/v2/historical-data/datasets/${runDataset.dataset_id}/csv`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-medium text-slate-200 flex items-center gap-1.5 transition"
                    >
                      <Download className="w-3.5 h-3.5 text-emerald-400" />
                      Export CSV
                    </a>
                  )}
                  <div className="text-right text-[11px] text-slate-400">
                    <div>Status: <span className="text-emerald-400 font-semibold">{runDataset?.completeness_status || 'COMPLETE'}</span></div>
                    <div>Source: <span className="text-white">{selectedRun.data_source || 'LOCAL_CACHE'}</span></div>
                  </div>
                </div>
              </div>

              {/* Economic Deterministic Fingerprint Strip */}
              <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-indigo-950/80 border border-indigo-800/60 flex items-center justify-center text-indigo-400">
                    <Fingerprint className="w-6 h-6" />
                  </div>
                  <div>
                    <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
                      Deterministic Economic Fingerprint
                    </div>
                    <div className="font-mono text-xs text-indigo-300 break-all select-all font-bold">
                      {selectedRun.deterministic_fingerprint || 'Pending'}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <Clock className="w-3.5 h-3.5" />
                  <span>Execution: {new Date(selectedRun.completed_at).toLocaleTimeString()}</span>
                </div>
              </div>

              {/* KPI Cards Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
                  <div className="text-xs text-slate-400 mb-1">Final Simulated Equity</div>
                  <div className="text-xl font-bold text-white font-mono">
                    ${metrics.final_equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </div>
                  <div className={`text-xs mt-1 font-semibold ${metrics.net_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {metrics.net_pnl >= 0 ? '+' : ''}${metrics.net_pnl.toFixed(2)} ({metrics.net_return_pct.toFixed(2)}%)
                  </div>
                </div>

                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
                  <div className="text-xs text-slate-400 mb-1">Risk Ratios (1m)</div>
                  <div className="text-xl font-bold text-white font-mono">
                    {metrics.sharpe_ratio !== null ? metrics.sharpe_ratio.toFixed(2) : 'N/A'}
                  </div>
                  <div className="text-xs mt-1 text-slate-400">
                    Sortino: {metrics.sortino_ratio !== null ? metrics.sortino_ratio.toFixed(2) : 'N/A'}
                  </div>
                </div>

                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
                  <div className="text-xs text-slate-400 mb-1">Max Drawdown</div>
                  <div className="text-xl font-bold text-rose-400 font-mono">
                    -{metrics.max_drawdown_pct.toFixed(2)}%
                  </div>
                  <div className="text-xs mt-1 text-slate-400">
                    -${metrics.max_drawdown_usd.toFixed(2)} USD
                  </div>
                </div>

                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
                  <div className="text-xs text-slate-400 mb-1">Win Rate & Trades</div>
                  <div className="text-xl font-bold text-white font-mono">
                    {metrics.win_rate_pct.toFixed(1)}%
                  </div>
                  <div className="text-xs mt-1 text-slate-400">
                    {metrics.total_trades} trades • PF: {metrics.profit_factor !== null ? metrics.profit_factor.toFixed(2) : '1.0'}
                  </div>
                </div>
              </div>

              {/* Tab Navigation */}
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-2">
                <button
                  onClick={() => setActiveTab('chart')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
                    activeTab === 'chart'
                      ? 'bg-gradient-to-r from-indigo-600 to-emerald-600 text-white shadow'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <CandlestickChart className="w-3.5 h-3.5" />
                  Trade Chart & Explorer ({chartBundle?.fills?.length ?? trades.length})
                </button>
                <button
                  onClick={() => setActiveTab('metrics')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    activeTab === 'metrics'
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Quantitative Breakdown
                </button>
                <button
                  onClick={() => setActiveTab('trades')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    activeTab === 'trades'
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Trades & Fills ({trades.length})
                </button>
                <button
                  onClick={() => setActiveTab('equity')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    activeTab === 'equity'
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Equity Time Series ({equityCurve.length})
                </button>
                <button
                  onClick={() => setActiveTab('provenance')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    activeTab === 'provenance'
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Data Provenance Audit
                </button>
                <button
                  onClick={() => setActiveTab('experiments')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    activeTab === 'experiments'
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Experiments ({experiments.length})
                </button>
              </div>

              {/* Tab Content */}
              <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 flex-1 overflow-y-auto min-h-[300px]">
                {activeTab === 'chart' && (
                  <div className="space-y-5">
                    {/* Multi-symbol selector if applicable */}
                    {chartBundle && chartBundle.symbols.length > 1 && (
                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-slate-400">Chart Symbol:</span>
                        {chartBundle.symbols.map((sym) => (
                          <button
                            key={sym}
                            type="button"
                            onClick={() => setChartSymbol(sym)}
                            className={`px-2.5 py-1 rounded-md font-mono font-semibold border ${
                              chartSymbol === sym
                                ? 'bg-indigo-600 text-white border-indigo-500'
                                : 'bg-slate-950 text-slate-300 border-slate-800 hover:border-slate-700'
                            }`}
                          >
                            {sym}
                          </button>
                        ))}
                      </div>
                    )}

                    {/* TradingView Multi-Pane Interactive Chart */}
                    {chartLoading ? (
                      <div className="h-[420px] flex items-center justify-center text-slate-400 text-xs gap-2">
                        <RotateCcw className="w-4 h-4 animate-spin text-indigo-400" />
                        Loading historical OHLCV candles, indicators & execution ledger...
                      </div>
                    ) : chartBundle ? (
                      <BacktestTradeChart
                        key={`${chartBundle.run_id}_${chartSymbol || chartBundle.symbols[0] || ''}`}
                        bundle={chartBundle}
                        activeSymbol={chartSymbol || chartBundle.symbols[0] || ''}
                        filteredFills={filteredFills}
                        selectedFillId={selectedFillId}
                        focusRequest={focusRequest}
                        onSelectFill={handleSelectFillFromChart}
                      />
                    ) : (
                      <div className="p-8 text-center text-slate-500 text-xs">
                        Chart bundle unavailable for this run.
                      </div>
                    )}

                    {/* Trade Explorer Panel (Bidirectional with Chart) */}
                    {chartBundle && (
                      <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
                          <div className="flex items-center gap-2">
                            <BookOpen className="w-4 h-4 text-emerald-400" />
                            <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                              Bidirectional Trade Explorer
                            </h3>
                            <span className="text-[10px] text-slate-400 font-mono">
                              (Click any row to zoom chart to candle)
                            </span>
                          </div>

                          {/* Sub-view Switcher */}
                          <div className="flex items-center gap-1.5 text-[11px] font-mono">
                            <button
                              type="button"
                              onClick={() => setExplorerView('fills')}
                              className={`px-2.5 py-1 rounded border ${
                                explorerView === 'fills'
                                  ? 'bg-indigo-600 text-white border-indigo-500'
                                  : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-white'
                              }`}
                            >
                              Execution Fills ({filteredFills.length})
                            </button>
                            <button
                              type="button"
                              onClick={() => setExplorerView('closed_trades')}
                              className={`px-2.5 py-1 rounded border ${
                                explorerView === 'closed_trades'
                                  ? 'bg-indigo-600 text-white border-indigo-500'
                                  : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-white'
                              }`}
                            >
                              Closed Trades Entry ↔ Exit ({filteredClosedTrades.length})
                            </button>
                            <button
                              type="button"
                              onClick={() => setExplorerView('ledger')}
                              className={`px-2.5 py-1 rounded border ${
                                explorerView === 'ledger'
                                  ? 'bg-indigo-600 text-white border-indigo-500'
                                  : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-white'
                              }`}
                            >
                              Portfolio Ledger ({chartBundle.portfolio_transactions?.length || 0})
                            </button>
                          </div>
                        </div>

                        {/* Filter Controls */}
                        <div className="flex flex-wrap items-center gap-2.5 text-[11px]">
                          <div className="flex items-center gap-1 text-slate-400">
                            <Filter className="w-3.5 h-3.5" />
                            <span>Filters:</span>
                          </div>

                          {explorerView === 'fills' && (
                            <select
                              value={filterSide}
                              onChange={(e: any) => setFilterSide(e.target.value)}
                              className="bg-slate-900 border border-slate-800 rounded px-2 py-1 text-white"
                            >
                              <option value="ALL">All Sides (BUY/SELL)</option>
                              <option value="BUY">BUY Only</option>
                              <option value="SELL">SELL Only</option>
                            </select>
                          )}

                          <select
                            value={filterOutcome}
                            onChange={(e: any) => setFilterOutcome(e.target.value)}
                            className="bg-slate-900 border border-slate-800 rounded px-2 py-1 text-white"
                          >
                            <option value="ALL">All Outcomes</option>
                            <option value="WIN">Winning Only</option>
                            <option value="LOSS">Losing Only</option>
                          </select>

                          <select
                            value={filterSymbol}
                            onChange={(e) => setFilterSymbol(e.target.value)}
                            className="bg-slate-900 border border-slate-800 rounded px-2 py-1 text-white"
                          >
                            <option value="ALL">All Symbols</option>
                            {availableFilterSymbols.map((s) => (
                              <option key={s} value={s}>{s}</option>
                            ))}
                          </select>

                          <select
                            value={filterStrategy}
                            onChange={(e) => setFilterStrategy(e.target.value)}
                            className="bg-slate-900 border border-slate-800 rounded px-2 py-1 text-white"
                          >
                            <option value="ALL">All Strategies</option>
                            {availableFilterStrategies.map((st) => (
                              <option key={st} value={st}>{st}</option>
                            ))}
                          </select>

                          <div className="relative flex-1 min-w-[160px]">
                            <Search className="w-3 h-3 text-slate-500 absolute left-2.5 top-2" />
                            <input
                              type="text"
                              value={filterSearch}
                              onChange={(e) => setFilterSearch(e.target.value)}
                              placeholder="Search Order ID, Fill ID, reason..."
                              className="w-full bg-slate-900 border border-slate-800 rounded pl-7 pr-2.5 py-1 text-white placeholder-slate-500 font-mono"
                            />
                          </div>
                        </div>

                        {/* View 1: Simulated Fills Table */}
                        {explorerView === 'fills' && (
                          <div className="overflow-x-auto max-h-[340px]">
                            <table className="w-full text-left text-[11px] font-mono">
                              <thead className="bg-slate-900 text-slate-400 border-b border-slate-800 sticky top-0">
                                <tr>
                                  <th className="py-2 px-2.5">Fill Time (UTC)</th>
                                  <th className="py-2 px-2.5">Order / Fill ID</th>
                                  <th className="py-2 px-2.5">Symbol</th>
                                  <th className="py-2 px-2.5">Side</th>
                                  <th className="py-2 px-2.5">Qty</th>
                                  <th className="py-2 px-2.5">Exec Price</th>
                                  <th className="py-2 px-2.5">Fee / Slip</th>
                                  <th className="py-2 px-2.5">Closed P&L</th>
                                  <th className="py-2 px-2.5">Strategy Reason</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                                {filteredFills.length === 0 ? (
                                  <tr>
                                    <td colSpan={9} className="py-6 text-center text-slate-500">
                                      No simulated fills match current filters.
                                    </td>
                                  </tr>
                                ) : (
                                  filteredFills.map((f) => {
                                    const isSelected = selectedFillId === f.simulated_fill_id
                                    const isBuy = f.side.toUpperCase() === 'BUY'
                                    const linked = linkedTradeByFillId.get(f.simulated_fill_id)
                                    const isExitOfTrade = linked && linked.exit_fill_id === f.simulated_fill_id
                                    return (
                                      <tr
                                        key={f.simulated_fill_id}
                                        ref={(el) => {
                                          fillRowRefs.current[f.simulated_fill_id] = el
                                        }}
                                        onClick={() => handleZoomToFill(f)}
                                        className={`cursor-pointer transition ${
                                          isSelected
                                            ? 'bg-indigo-950/70 ring-1 ring-inset ring-yellow-400/60'
                                            : 'hover:bg-slate-900/70'
                                        }`}
                                      >
                                        <td className="py-2 px-2.5 whitespace-nowrap text-slate-300">
                                          {f.fill_time.replace('T', ' ').slice(0, 19)}
                                        </td>
                                        <td className="py-2 px-2.5">
                                          <div className="text-white font-semibold">{f.simulated_order_id}</div>
                                          <div className="text-[10px] text-slate-500">{f.simulated_fill_id}</div>
                                        </td>
                                        <td className="py-2 px-2.5 font-semibold text-white">{f.symbol}</td>
                                        <td className="py-2 px-2.5">
                                          <span className={`inline-flex items-center gap-0.5 font-bold ${isBuy ? 'text-emerald-400' : 'text-rose-400'}`}>
                                            {isBuy ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                                            {f.side}
                                          </span>
                                          {f.is_partial_fill && (
                                            <span className="ml-1 px-1 py-0.2 rounded bg-amber-950 text-amber-300 text-[9px]">P</span>
                                          )}
                                        </td>
                                        <td className="py-2 px-2.5">{f.fill_qty}</td>
                                        <td className="py-2 px-2.5 font-semibold text-white">${f.fill_price.toFixed(4)}</td>
                                        <td className="py-2 px-2.5 text-slate-400">${f.fee.toFixed(2)} / ${f.slippage.toFixed(4)}</td>
                                        <td className="py-2 px-2.5">
                                          {isExitOfTrade && linked ? (
                                            <span className={`font-bold ${linked.net_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                              {linked.net_pnl >= 0 ? '+' : ''}${linked.net_pnl.toFixed(2)}
                                            </span>
                                          ) : (
                                            <span className="text-slate-600">—</span>
                                          )}
                                        </td>
                                        <td className="py-2 px-2.5 text-[10px] text-sky-300 max-w-[220px] truncate" title={f.strategy_reason || ''}>
                                          {f.strategy_reason || 'Strategy Signal'}
                                        </td>
                                      </tr>
                                    )
                                  })
                                )}
                              </tbody>
                            </table>
                          </div>
                        )}

                        {/* View 2: Closed Trades Table (Linked Entry -> Exit) */}
                        {explorerView === 'closed_trades' && (
                          <div className="overflow-x-auto max-h-[340px]">
                            <table className="w-full text-left text-[11px] font-mono">
                              <thead className="bg-slate-900 text-slate-400 border-b border-slate-800 sticky top-0">
                                <tr>
                                  <th className="py-2 px-2.5">Trade ID</th>
                                  <th className="py-2 px-2.5">Symbol / Dir</th>
                                  <th className="py-2 px-2.5">Entry (UTC @ Price)</th>
                                  <th className="py-2 px-2.5">Exit (UTC @ Price)</th>
                                  <th className="py-2 px-2.5">Qty</th>
                                  <th className="py-2 px-2.5">Fees</th>
                                  <th className="py-2 px-2.5">Net P&L</th>
                                  <th className="py-2 px-2.5">Hold</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                                {filteredClosedTrades.length === 0 ? (
                                  <tr>
                                    <td colSpan={8} className="py-6 text-center text-slate-500">
                                      No closed round-trip trades matched current filters.
                                    </td>
                                  </tr>
                                ) : (
                                  filteredClosedTrades.map((tr) => (
                                    <tr
                                      key={tr.trade_id}
                                      onClick={() => handleZoomToClosedTrade(tr)}
                                      className="hover:bg-indigo-950/40 cursor-pointer transition"
                                    >
                                      <td className="py-2 px-2.5 text-white font-semibold">{tr.trade_id}</td>
                                      <td className="py-2 px-2.5">
                                        <span className="font-semibold text-white">{tr.symbol}</span>{' '}
                                        <span className="text-[10px] text-emerald-400">{tr.direction}</span>
                                      </td>
                                      <td className="py-2 px-2.5">
                                        <div>{tr.entry_time.replace('T', ' ').slice(0, 19)}</div>
                                        <div className="text-[10px] text-emerald-300">${tr.entry_price.toFixed(4)}</div>
                                      </td>
                                      <td className="py-2 px-2.5">
                                        <div>{tr.exit_time.replace('T', ' ').slice(0, 19)}</div>
                                        <div className="text-[10px] text-rose-300">${tr.exit_price.toFixed(4)}</div>
                                      </td>
                                      <td className="py-2 px-2.5">{tr.qty}</td>
                                      <td className="py-2 px-2.5 text-slate-400">${tr.fees.toFixed(2)}</td>
                                      <td className={`py-2 px-2.5 font-bold ${tr.net_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                        {tr.net_pnl >= 0 ? '+' : ''}${tr.net_pnl.toFixed(2)} ({tr.return_pct.toFixed(2)}%)
                                      </td>
                                      <td className="py-2 px-2.5 text-slate-400">{Math.round(tr.duration_seconds / 60)}m</td>
                                    </tr>
                                  ))
                                )}
                              </tbody>
                            </table>
                          </div>
                        )}

                        {/* View 3: Portfolio Ledger Transactions */}
                        {explorerView === 'ledger' && (
                          <div className="overflow-x-auto max-h-[340px]">
                            <table className="w-full text-left text-[11px] font-mono">
                              <thead className="bg-slate-900 text-slate-400 border-b border-slate-800 sticky top-0">
                                <tr>
                                  <th className="py-2 px-2.5">Timestamp (UTC)</th>
                                  <th className="py-2 px-2.5">Type</th>
                                  <th className="py-2 px-2.5">Amount ($)</th>
                                  <th className="py-2 px-2.5">Cash After ($)</th>
                                  <th className="py-2 px-2.5">Reference ID</th>
                                  <th className="py-2 px-2.5">Description</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                                {(chartBundle.portfolio_transactions || []).map((tx) => (
                                  <tr key={tx.transaction_id} className="hover:bg-slate-900/60">
                                    <td className="py-1.5 px-2.5 whitespace-nowrap">{tx.timestamp.replace('T', ' ').slice(0, 19)}</td>
                                    <td className="py-1.5 px-2.5 font-semibold text-indigo-300">{tx.transaction_type}</td>
                                    <td className={`py-1.5 px-2.5 font-semibold ${tx.amount >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                      {tx.amount >= 0 ? '+' : ''}${tx.amount.toFixed(2)}
                                    </td>
                                    <td className="py-1.5 px-2.5 text-white">${tx.cash_after.toFixed(2)}</td>
                                    <td className="py-1.5 px-2.5 text-slate-400">{tx.reference_id || '—'}</td>
                                    <td className="py-1.5 px-2.5 text-slate-400">{tx.description}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'metrics' && (
                  <div className="space-y-4 text-xs">
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                      <div className="p-3 bg-slate-950/70 rounded-lg border border-slate-800">
                        <span className="text-slate-400">Realized PnL:</span>
                        <div className="text-sm font-bold font-mono text-white mt-1">
                          ${metrics.realized_pnl.toFixed(2)}
                        </div>
                      </div>
                      <div className="p-3 bg-slate-950/70 rounded-lg border border-slate-800">
                        <span className="text-slate-400">Total Commissions:</span>
                        <div className="text-sm font-bold font-mono text-white mt-1">
                          ${metrics.total_fees.toFixed(2)}
                        </div>
                      </div>
                      <div className="p-3 bg-slate-950/70 rounded-lg border border-slate-800">
                        <span className="text-slate-400">Slippage Impact:</span>
                        <div className="text-sm font-bold font-mono text-white mt-1">
                          ${metrics.total_slippage.toFixed(2)}
                        </div>
                      </div>
                      <div className="p-3 bg-slate-950/70 rounded-lg border border-slate-800">
                        <span className="text-slate-400">Total Turnover:</span>
                        <div className="text-sm font-bold font-mono text-white mt-1">
                          ${metrics.turnover_usd.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </div>
                      </div>
                      <div className="p-3 bg-slate-950/70 rounded-lg border border-slate-800">
                        <span className="text-slate-400">Time In Market:</span>
                        <div className="text-sm font-bold font-mono text-white mt-1">
                          {metrics.time_in_market_pct.toFixed(2)}%
                        </div>
                      </div>
                      <div className="p-3 bg-slate-950/70 rounded-lg border border-slate-800">
                        <span className="text-slate-400">Annualization Sampling:</span>
                        <div className="text-sm font-bold font-mono text-white mt-1">
                          {metrics.annualization_sampling} (√{metrics.annualization_factor.toFixed(1)})
                        </div>
                      </div>
                    </div>

                    <div className="p-3 bg-slate-950/50 rounded-lg border border-slate-800/80 text-slate-400 text-[11px] leading-relaxed">
                      <strong>Legal & Research Disclaimer:</strong> {metrics.disclaimer}
                    </div>
                  </div>
                )}

                {activeTab === 'provenance' && (
                  <div className="space-y-4 text-xs font-mono">
                    <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">
                      <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                        Dataset Provenance Metadata (GĐ41 Audit)
                      </h3>
                      {runDataset ? (
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-[11px]">
                          <div><span className="text-slate-500">Provider:</span> <span className="text-emerald-400 font-bold">{runDataset.provider}</span></div>
                          <div><span className="text-slate-500">Source Type:</span> <span className="text-white font-bold">{runDataset.source_type}</span></div>
                          <div><span className="text-slate-500">Asset Class:</span> <span className="text-white">{runDataset.asset_class}</span></div>
                          <div><span className="text-slate-500">Stock/Crypto Feed:</span> <span className="text-indigo-400 font-bold">{runDataset.feed}</span></div>
                          <div><span className="text-slate-500">Total Bars:</span> <span className="text-white font-bold">{runDataset.total_bars}</span></div>
                          <div><span className="text-slate-500">Timeframe:</span> <span className="text-white">{runDataset.timeframe || '1m'}</span></div>
                          <div><span className="text-slate-500">Start Time:</span> <span className="text-slate-300">{runDataset.start_time}</span></div>
                          <div><span className="text-slate-500">End Time:</span> <span className="text-slate-300">{runDataset.end_time}</span></div>
                          <div><span className="text-slate-500">Completeness:</span> <span className="text-emerald-400 font-semibold">{runDataset.completeness_status || 'COMPLETE'}</span></div>
                          <div><span className="text-slate-500">Duplicates Removed:</span> <span className="text-slate-300">{runDataset.duplicate_count ?? 0}</span></div>
                          <div><span className="text-slate-500">Gaps Detected:</span> <span className="text-slate-300">{runDataset.gap_count ?? 0}</span></div>
                          <div><span className="text-slate-500">Adjustment Policy:</span> <span className="text-slate-300">{runDataset.adjustment_policy || 'RAW'}</span></div>
                          <div className="col-span-2 md:col-span-3">
                            <span className="text-slate-500">SHA-256 Checksum:</span>
                            <div className="text-xs text-indigo-300 select-all font-bold break-all mt-0.5">
                              {runDataset.checksum_sha256}
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="text-slate-500">No dataset manifest attached to this run.</div>
                      )}
                    </div>
                  </div>
                )}

                {activeTab === 'trades' && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800">
                        <tr>
                          <th className="py-2 px-3">Time</th>
                          <th className="py-2 px-3">Symbol</th>
                          <th className="py-2 px-3">Side</th>
                          <th className="py-2 px-3">Qty</th>
                          <th className="py-2 px-3">Price</th>
                          <th className="py-2 px-3">Fee</th>
                          <th className="py-2 px-3">Slippage</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 text-slate-300">
                        {trades.length === 0 ? (
                          <tr>
                            <td colSpan={7} className="py-4 text-center text-slate-500">
                              No trades generated during this run.
                            </td>
                          </tr>
                        ) : (
                          trades.map((t, idx) => (
                            <tr key={idx} className="hover:bg-slate-950/40">
                              <td className="py-2 px-3">{new Date(t.fill_time).toLocaleTimeString()}</td>
                              <td className="py-2 px-3 font-semibold text-white">{t.symbol}</td>
                              <td className="py-2 px-3">
                                <span className={t.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}>
                                  {t.side}
                                </span>
                              </td>
                              <td className="py-2 px-3">{t.fill_qty}</td>
                              <td className="py-2 px-3">${t.fill_price.toFixed(2)}</td>
                              <td className="py-2 px-3 text-slate-400">${t.fee.toFixed(2)}</td>
                              <td className="py-2 px-3 text-slate-400">${t.slippage.toFixed(4)}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                )}

                {activeTab === 'equity' && (
                  <div className="overflow-x-auto max-h-[350px]">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 sticky top-0">
                        <tr>
                          <th className="py-2 px-3">Bar Time</th>
                          <th className="py-2 px-3">Equity ($)</th>
                          <th className="py-2 px-3">Cash ($)</th>
                          <th className="py-2 px-3">Unrealized PnL ($)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 text-slate-300">
                        {equityCurve.map((pt, idx) => (
                          <tr key={idx} className="hover:bg-slate-950/40">
                            <td className="py-1.5 px-3">{new Date(pt.timestamp).toLocaleTimeString()}</td>
                            <td className="py-1.5 px-3 font-semibold text-white">${pt.equity.toFixed(2)}</td>
                            <td className="py-1.5 px-3 text-slate-400">${pt.cash.toFixed(2)}</td>
                            <td className="py-1.5 px-3 text-slate-400">${pt.unrealized_pnl.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {activeTab === 'experiments' && (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                      <div className="flex items-center gap-2">
                        <label className="text-xs text-slate-400">Select Experiment:</label>
                        <select
                          value={selectedExpId}
                          onChange={(e) => setSelectedExpId(e.target.value)}
                          className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1 text-xs text-white"
                        >
                          {experiments.length === 0 ? (
                            <option value="">No experiments recorded</option>
                          ) : (
                            experiments.map((exp: any) => (
                              <option key={exp.experiment_id} value={exp.experiment_id}>
                                {exp.name || exp.experiment_id} ({exp.variants?.length || 0} variants)
                              </option>
                            ))
                          )}
                        </select>
                      </div>
                      <button
                        onClick={fetchExperiments}
                        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-300"
                      >
                        Refresh
                      </button>
                    </div>

                    {comparisonData?.comparison_table ? (
                      <div className="overflow-x-auto max-h-[400px]">
                        <table className="w-full text-left text-xs font-mono">
                          <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 sticky top-0">
                            <tr>
                              <th className="py-2 px-3">Variant</th>
                              <th className="py-2 px-3">Comparability</th>
                              <th className="py-2 px-3">Return (%)</th>
                              <th className="py-2 px-3">Sharpe</th>
                              <th className="py-2 px-3">MDD (%)</th>
                              <th className="py-2 px-3">Trades</th>
                              <th className="py-2 px-3">Win Rate</th>
                              <th className="py-2 px-3">Δ Sharpe</th>
                              <th className="py-2 px-3">Δ Return</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60 text-slate-300">
                            {comparisonData.comparison_table.map((row: any, idx: number) => (
                              <tr key={idx} className={`hover:bg-slate-950/40 ${row.is_baseline ? 'bg-indigo-950/30' : ''}`}>
                                <td className="py-2 px-3 font-semibold text-white">
                                  {row.name} {row.is_baseline && <span className="text-[10px] text-indigo-400 font-normal">(Base)</span>}
                                </td>
                                <td className="py-2 px-3">
                                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                                    row.is_comparable ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-amber-950 text-amber-400 border border-amber-800'
                                  }`}>
                                    {row.comparability_status}
                                  </span>
                                </td>
                                <td className={`py-2 px-3 font-semibold ${row.total_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                  {row.total_return_pct.toFixed(2)}%
                                </td>
                                <td className="py-2 px-3">{row.sharpe_ratio.toFixed(2)}</td>
                                <td className="py-2 px-3 text-rose-400">-{row.max_drawdown_pct.toFixed(2)}%</td>
                                <td className="py-2 px-3">{row.total_trades}</td>
                                <td className="py-2 px-3">{row.win_rate_pct.toFixed(1)}%</td>
                                <td className={`py-2 px-3 font-bold ${row.delta_sharpe >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                  {row.delta_sharpe >= 0 ? '+' : ''}{row.delta_sharpe.toFixed(2)}
                                </td>
                                <td className={`py-2 px-3 font-bold ${row.delta_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                  {row.delta_return_pct >= 0 ? '+' : ''}{row.delta_return_pct.toFixed(2)}%
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="py-8 text-center text-slate-500 text-xs">
                        Select an experiment above to view comparative KPI tables and delta analysis.
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-12 text-center text-slate-500 text-sm flex-1 flex flex-col items-center justify-center">
              <Database className="w-10 h-10 text-slate-600 mb-3" />
              Select a backtest run on the left or launch a new simulation from Alpaca historical data.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
