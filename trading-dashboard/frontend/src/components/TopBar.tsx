import React from 'react'
import {
  Radio,
  PlayCircle,
  ShieldAlert,
  Cpu,
  Coins,
  TrendingUp,
  BarChart2,
  LineChart,
  Briefcase,
  Activity,
  ShieldCheck,
  Sliders,
  Bot,
  Database
} from 'lucide-react'
import type { PipelineStatus, AssetType, DashboardTab } from '../types'

interface TopBarProps {
  assetType: AssetType
  onChangeAssetType: (type: AssetType) => void
  selectedSymbol: string
  onSelectSymbol: (symbol: string) => void
  currentPrice: number | null
  priceChange: number
  priceChangePercent: number
  wsConnected: boolean
  isReplayMode: boolean
  onToggleReplay: () => void
  pipelineStatus: PipelineStatus | null
  activeTab: DashboardTab
  onChangeTab: (tab: DashboardTab) => void
}

export const TopBar: React.FC<TopBarProps> = ({
  assetType,
  onChangeAssetType,
  selectedSymbol,
  onSelectSymbol,
  currentPrice,
  priceChange,
  priceChangePercent,
  wsConnected,
  isReplayMode,
  onToggleReplay,
  pipelineStatus,
  activeTab,
  onChangeTab,
}) => {
  const getMarketBadge = () => {
    if (isReplayMode) {
      return (
        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-purple-900/60 text-purple-300 border border-purple-500/40 text-xs font-semibold uppercase tracking-wider">
          <PlayCircle className="w-3.5 h-3.5 text-purple-400 animate-pulse" />
          HISTORICAL REPLAY
        </span>
      )
    }

    if (assetType === 'CRYPTO') {
      const cMode = pipelineStatus?.crypto_mode || 'LIVE STREAMING'
      const label = pipelineStatus?.crypto_latency_label || '24/7 Crypto Market'
      if (cMode === 'LIVE STREAMING' || cMode.includes('LIVE')) {
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-900/60 text-emerald-300 border border-emerald-500/40 text-xs font-semibold uppercase tracking-wider" title={label}>
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            CRYPTO 24/7 LIVE
          </span>
        )
      }
      if (cMode === 'DELAYED DATA') {
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-900/60 text-amber-300 border border-amber-500/40 text-xs font-semibold uppercase tracking-wider" title={label}>
            <Radio className="w-3.5 h-3.5 text-amber-400" />
            CRYPTO DELAYED
          </span>
        )
      }
      if (cMode === 'STALE') {
        return (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-rose-900/60 text-rose-300 border border-rose-500/40 text-xs font-semibold uppercase tracking-wider" title={label}>
            <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
            CRYPTO 24/7 STALE
          </span>
        )
      }
      return (
        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 text-xs font-semibold uppercase tracking-wider" title={label}>
          <Coins className="w-3.5 h-3.5 text-emerald-400" />
          CRYPTO 24/7 ACTIVE
        </span>
      )
    }

    // Stocks Status Badge
    const status = pipelineStatus?.market_status || 'MARKET CLOSED'
    if (status === 'LIVE STREAMING') {
      return (
        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-900/60 text-emerald-300 border border-emerald-500/40 text-xs font-semibold uppercase tracking-wider" title={pipelineStatus?.latency_label}>
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
          STOCKS: LIVE STREAMING
        </span>
      )
    }
    if (status === 'DELAYED DATA') {
      const delayMin = pipelineStatus?.market_delay_minutes || 15
      return (
        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-900/60 text-amber-300 border border-amber-500/40 text-xs font-semibold uppercase tracking-wider" title={pipelineStatus?.latency_label}>
          <Radio className="w-3.5 h-3.5 text-amber-400" />
          STOCKS: DELAYED ({delayMin}m)
        </span>
      )
    }
    if (status === 'STALE') {
      return (
        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-rose-900/60 text-rose-300 border border-rose-500/40 text-xs font-semibold uppercase tracking-wider" title={pipelineStatus?.latency_label}>
          <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
          STOCKS: STALE DATA
        </span>
      )
    }
    if (status === 'RECONNECTING') {
      return (
        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-yellow-900/60 text-yellow-300 border border-yellow-500/40 text-xs font-semibold uppercase tracking-wider" title={pipelineStatus?.latency_label}>
          <Radio className="w-3.5 h-3.5 text-yellow-400 animate-spin" />
          RECONNECTING
        </span>
      )
    }
    if (status === 'ERROR') {
      return (
        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-red-900/60 text-red-300 border border-red-500/40 text-xs font-semibold uppercase tracking-wider" title={pipelineStatus?.latency_label}>
          <ShieldAlert className="w-3.5 h-3.5 text-red-400" />
          PRODUCER ERROR
        </span>
      )
    }
    return (
      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700 text-xs font-semibold uppercase tracking-wider" title={pipelineStatus?.latency_label}>
        <Radio className="w-3.5 h-3.5 text-slate-400" />
        STOCKS: MARKET CLOSED (NORMAL)
      </span>
    )
  }

  const isPositive = priceChange >= 0
  const stockSymbols = ['NVDA', 'AAPL']
  const cryptoSymbols = ['BTC/USD', 'ETH/USD']
  const activeSymbols = assetType === 'STOCKS' ? stockSymbols : cryptoSymbols

  const tabs: Array<{ id: DashboardTab; label: string; icon: React.ReactNode }> = [
    { id: 'terminal', label: 'Terminal', icon: <BarChart2 className="w-3.5 h-3.5" /> },
    { id: 'analytics', label: 'Strategy Analytics', icon: <LineChart className="w-3.5 h-3.5" /> },
    { id: 'portfolio', label: 'Paper Portfolio', icon: <Briefcase className="w-3.5 h-3.5" /> },
    { id: 'workbench', label: 'Trading Workbench', icon: <Sliders className="w-3.5 h-3.5" /> },
    { id: 'paper_bot', label: 'V2 Paper Bot', icon: <Bot className="w-3.5 h-3.5 text-emerald-400" /> },
    { id: 'backtesting', label: 'V2 Backtest', icon: <Database className="w-3.5 h-3.5 text-indigo-400" /> },
    { id: 'observability', label: 'Streaming Observability', icon: <Activity className="w-3.5 h-3.5" /> },
    { id: 'reliability', label: 'Reliability & Logs', icon: <ShieldCheck className="w-3.5 h-3.5" /> },
  ]

  return (
    <header className="bg-slate-900/95 border-b border-slate-800 flex flex-col select-none backdrop-blur sticky top-0 z-30 shadow-md">
      {/* Upper Row: Brand, Asset Selector, Symbols, Ticker & Controls */}
      <div className="px-4 py-2.5 flex flex-wrap items-center justify-between gap-4">
        {/* Brand & Mode */}
        <div className="flex items-center gap-3 sm:gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-blue-600/20 border border-blue-500/30 rounded-lg text-blue-400">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-wider text-slate-100 flex items-center gap-2">
                QUANT TERMINAL
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 font-mono">
                  v2.5 QUANT
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-mono font-bold">
                  DRY_RUN
                </span>
              </h1>
              <p className="text-[10px] text-slate-400 font-mono">Redpanda + Flink + Alpaca 24/7</p>
            </div>
          </div>

          <div className="h-6 w-[1px] bg-slate-800 hidden sm:block" />

          {/* Asset Class Selector (STOCKS vs CRYPTO) */}
          <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800">
            <button
              onClick={() => onChangeAssetType('STOCKS')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-bold transition-all ${
                assetType === 'STOCKS'
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <TrendingUp className="w-3 h-3" />
              STOCKS
            </button>
            <button
              onClick={() => onChangeAssetType('CRYPTO')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-bold transition-all ${
                assetType === 'CRYPTO'
                  ? 'bg-amber-600 text-white shadow-lg shadow-amber-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Coins className="w-3 h-3 text-amber-300" />
              CRYPTO 24/7
            </button>
          </div>

          {/* Symbol Selector Buttons for Current Asset Class */}
          <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800">
            {activeSymbols.map((sym) => (
              <button
                key={sym}
                onClick={() => onSelectSymbol(sym)}
                className={`px-3 py-1 rounded-md text-xs font-bold transition-all ${
                  selectedSymbol === sym
                    ? assetType === 'CRYPTO'
                      ? 'bg-amber-600 text-white shadow-lg shadow-amber-500/20'
                      : 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>

          {/* Current Price Display */}
          {currentPrice !== null && (
            <div className="flex items-baseline gap-2 font-mono">
              <span className="text-lg font-bold text-slate-100">
                ${currentPrice >= 1000 ? currentPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : currentPrice.toFixed(2)}
              </span>
              <span
                className={`text-xs font-semibold ${
                  isPositive ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {isPositive ? '+' : ''}
                {priceChange.toFixed(2)} ({isPositive ? '+' : ''}
                {priceChangePercent.toFixed(2)}%)
              </span>
            </div>
          )}
        </div>

        {/* Center / Right Status & Controls */}
        <div className="flex items-center gap-3">
          {/* Market Status Badge */}
          {getMarketBadge()}

          {/* Replay Mode Toggle */}
          <button
            onClick={onToggleReplay}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-bold transition-all border ${
              isReplayMode
                ? 'bg-purple-600 text-white border-purple-400 shadow-lg shadow-purple-500/20'
                : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700'
            }`}
          >
            <PlayCircle className="w-3.5 h-3.5" />
            {isReplayMode ? 'Exit Replay' : 'Historical Replay'}
          </button>

          {/* WebSocket Transport Connection Indicator */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-mono border ${
              wsConnected
                ? 'bg-slate-800/80 text-emerald-400 border-slate-700'
                : 'bg-rose-950/60 text-rose-400 border-rose-800/60'
            }`}
            title={wsConnected ? 'WebSocket Transport Link: Connected to FastAPI Backend (/ws/live)' : 'WebSocket Transport Link: Disconnected'}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                wsConnected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'
              }`}
            />
            <span className="hidden sm:inline font-semibold">{wsConnected ? 'WS TRANSPORT: CONNECTED' : 'WS TRANSPORT: OFF'}</span>
          </div>
        </div>
      </div>

      {/* Navigation Tabs Bar */}
      <nav className="flex items-center gap-1 px-4 border-t border-slate-800/80 bg-slate-950/60 overflow-x-auto py-1">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => onChangeTab(tab.id)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded text-xs font-medium transition-all ${
                isActive
                  ? 'bg-blue-600/20 text-blue-300 border border-blue-500/40 shadow-sm font-semibold'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          )
        })}
      </nav>
    </header>
  )
}
export default TopBar
