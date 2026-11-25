import React, { useState, useEffect, useRef, useCallback } from 'react'
import type {
  V2BotSummary,
  V2Portfolio,
  V2SimulatedOrder,
  V2SimulatedFill,
  V2Performance,
  V2Health,
  V2SupervisorOverview,
} from '../types'
import {
  Bot,
  Play,
  Pause,
  RotateCcw,
  Square,
  PlusCircle,
  RefreshCw,
  Activity,
  Layers,
  TrendingUp,
  AlertTriangle,
  Briefcase,
  XCircle,
} from 'lucide-react'

interface PaperBotPanelProps {
  apiBase?: string
}

export const PaperBotPanel: React.FC<PaperBotPanelProps> = ({
  apiBase = 'http://127.0.0.1:8005'
}) => {
  // Bots list & current active selection
  const [bots, setBots] = useState<V2BotSummary[]>([])
  const [overview, setOverview] = useState<V2SupervisorOverview | null>(null)
  const [selectedSessionId, setSelectedSessionId] = useState<string>('')
  const [actionLoading, setActionLoading] = useState<boolean>(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Current bot detail data
  const [botSummary, setBotSummary] = useState<V2BotSummary | null>(null)
  const [portfolio, setPortfolio] = useState<V2Portfolio | null>(null)
  const [orders, setOrders] = useState<V2SimulatedOrder[]>([])
  const [fills, setFills] = useState<V2SimulatedFill[]>([])
  const [performance, setPerformance] = useState<V2Performance | null>(null)
  const [health, setHealth] = useState<V2Health | null>(null)
  const [wsConnected, setWsConnected] = useState<boolean>(false)
  const [activeSubTab, setActiveSubTab] = useState<'portfolio' | 'orders' | 'performance' | 'health'>('portfolio')

  // Real-time Event Log from WebSocket
  const [eventLogs, setEventLogs] = useState<Array<{ time: string; type: string; details: string }>>([])

  // Modal for creating new bot
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false)
  const [newBotId, setNewBotId] = useState<string>('paper_bot_' + Math.floor(Math.random() * 1000))
  const [newBotName, setNewBotName] = useState<string>('AlgoTrading V2 Alpha')
  const [newSymbols, setNewSymbols] = useState<string>('NVDA, BTC/USD')
  const [newStrategy, setNewStrategy] = useState<string>('MA_CROSS_1M')
  const [newInitialCash, setNewInitialCash] = useState<number>(100000)
  const [newStopPolicy, setNewStopPolicy] = useState<string>('CANCEL_REMAINDER')

  const wsRef = useRef<WebSocket | null>(null)
  const pollIntervalRef = useRef<any>(null)

  // 1. Fetch bots list & supervisor overview
  const fetchBots = useCallback(async () => {
    try {
      const [botsRes, ovRes] = await Promise.all([
        fetch(`${apiBase}/api/v2/bots`),
        fetch(`${apiBase}/api/v2/bots/overview`),
      ])
      if (botsRes.ok) {
        const data: V2BotSummary[] = await botsRes.json()
        setBots(data)
        if (data.length > 0) {
          if (!selectedSessionId || !data.some(b => b.session_id === selectedSessionId)) {
            setSelectedSessionId(data[0].session_id)
          }
        }
      }
      if (ovRes.ok) {
        setOverview(await ovRes.json())
      }
    } catch (err: any) {
      console.error('Failed to load bots:', err)
      setErrorMsg('Cannot connect to V2 Bot API: ' + err.message)
    }
  }, [apiBase, selectedSessionId])

  // 2. Fetch detailed state for selected bot
  const fetchBotDetail = useCallback(async (sessionId: string) => {
    if (!sessionId) return
    try {
      const [sumRes, portRes, ordRes, fillRes, perfRes, healRes] = await Promise.all([
        fetch(`${apiBase}/api/v2/bots/${sessionId}`),
        fetch(`${apiBase}/api/v2/bots/${sessionId}/portfolio`),
        fetch(`${apiBase}/api/v2/bots/${sessionId}/orders`),
        fetch(`${apiBase}/api/v2/bots/${sessionId}/fills?limit=50`),
        fetch(`${apiBase}/api/v2/bots/${sessionId}/performance`),
        fetch(`${apiBase}/api/v2/bots/${sessionId}/health`),
      ])

      if (sumRes.ok) setBotSummary(await sumRes.json())
      if (portRes.ok) setPortfolio(await portRes.json())
      if (ordRes.ok) setOrders(await ordRes.json())
      if (fillRes.ok) setFills(await fillRes.json())
      if (perfRes.ok) setPerformance(await perfRes.json())
      if (healRes.ok) setHealth(await healRes.json())
      setErrorMsg(null)
    } catch (err: any) {
      console.error('Error fetching bot details:', err)
    }
  }, [apiBase])

  useEffect(() => {
    fetchBots()
  }, [fetchBots])

  useEffect(() => {
    if (selectedSessionId) {
      fetchBotDetail(selectedSessionId)
    }
  }, [selectedSessionId, fetchBotDetail])

  // 3. WebSocket Real-Time Connection
  useEffect(() => {
    if (!selectedSessionId) return

    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = apiBase.replace(/^https?:\/\//, '')
    const wsUrl = `${wsProto}//${wsHost}/ws/v2/bots/${selectedSessionId}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setWsConnected(true)
      setEventLogs((prev) => [
        { time: new Date().toLocaleTimeString(), type: 'TRANSPORT', details: `Connected to stream ${selectedSessionId}` },
        ...prev.slice(0, 40),
      ])
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        const evType = msg.event_type || msg.type || 'EVENT'
        const payload = msg.payload !== undefined ? msg.payload : msg

        if (evType === 'SNAPSHOT' && payload && typeof payload === 'object') {
          if (payload.summary) setBotSummary(payload.summary)
          if (payload.portfolio) setPortfolio(payload.portfolio)
          if (payload.orders) setOrders(payload.orders)
          if (payload.fills) setFills(payload.fills)
          if (payload.health) setHealth(payload.health)
          if (payload.performance) setPerformance(payload.performance)
        } else if (evType === 'BOT_LIFECYCLE_EVENT') {
          fetchBotDetail(selectedSessionId)
        } else if (evType === 'FILL_EVENT') {
          fetchBotDetail(selectedSessionId)
        } else if (evType === 'PORTFOLIO_UPDATE' && payload) {
          setPortfolio(payload)
        }

        let detailsStr = ''
        try {
          if (typeof payload === 'string') {
            detailsStr = payload.slice(0, 90)
          } else if (payload !== undefined && payload !== null) {
            detailsStr = (JSON.stringify(payload) || '').slice(0, 90)
          }
        } catch (_) {
          detailsStr = String(payload || '').slice(0, 90)
        }

        setEventLogs((prev) => [
          { time: new Date().toLocaleTimeString(), type: evType, details: detailsStr },
          ...(Array.isArray(prev) ? prev : []).slice(0, 40),
        ])
      } catch (e) {
        console.error('Failed to parse WS msg:', e)
      }
    }

    ws.onclose = () => {
      setWsConnected(false)
    }

    ws.onerror = () => {
      setWsConnected(false)
    }

    // Ping interval for heartbeat
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'PING', timestamp: Date.now() }))
      }
    }, 15000)

    // Fallback polling every 5s
    pollIntervalRef.current = setInterval(() => {
      fetchBotDetail(selectedSessionId)
    }, 5000)

    return () => {
      clearInterval(pingInterval)
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
    }
  }, [selectedSessionId, apiBase, fetchBotDetail])

  // Lifecycle Action Handlers
  const handleLifecycleAction = async (action: 'start' | 'pause' | 'resume' | 'stop') => {
    if (!selectedSessionId) return
    setActionLoading(true)
    try {
      const res = await fetch(`${apiBase}/api/v2/bots/${selectedSessionId}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(action === 'stop' ? { policy: 'CANCEL_REMAINDER' } : { reason: 'UI_CLICK' }),
      })
      if (!res.ok) {
        const errData = await res.json()
        setErrorMsg(errData.detail || `Action ${action} failed`)
      } else {
        await fetchBots()
        await fetchBotDetail(selectedSessionId)
      }
    } catch (err: any) {
      setErrorMsg(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  // Create Bot Handler
  const handleCreateBot = async (e: React.FormEvent) => {
    e.preventDefault()
    setActionLoading(true)
    try {
      const symList = newSymbols.split(',').map((s) => s.trim().toUpperCase()).filter(Boolean)
      const res = await fetch(`${apiBase}/api/v2/bots`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bot_id: newBotId,
          bot_name: newBotName,
          symbols: symList,
          timeframe: '1m',
          initial_cash: newInitialCash,
          strategy_id: newStrategy,
          strategy_version: '1.0.0',
          stop_policy: newStopPolicy,
        }),
      })

      if (res.ok) {
        const created: V2BotSummary = await res.json()
        setShowCreateModal(false)
        await fetchBots()
        setSelectedSessionId(created.session_id)
      } else {
        const err = await res.json()
        setErrorMsg(err.detail || 'Failed to create bot')
      }
    } catch (err: any) {
      setErrorMsg(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  // Lifecycle status badge styling
  const getStatusBadge = (state?: string) => {
    switch (state) {
      case 'RUNNING':
        return (
          <span className="flex items-center gap-1.5 px-3 py-1 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-500/40 text-xs font-bold uppercase tracking-wider">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            RUNNING
          </span>
        )
      case 'PAUSED':
        return (
          <span className="flex items-center gap-1.5 px-3 py-1 rounded bg-amber-950/80 text-amber-400 border border-amber-500/40 text-xs font-bold uppercase tracking-wider">
            <Pause className="w-3.5 h-3.5 text-amber-400" />
            PAUSED
          </span>
        )
      case 'STOPPED':
        return (
          <span className="flex items-center gap-1.5 px-3 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700 text-xs font-bold uppercase tracking-wider">
            <Square className="w-3 h-3 text-slate-400" />
            STOPPED
          </span>
        )
      case 'ERROR':
        return (
          <span className="flex items-center gap-1.5 px-3 py-1 rounded bg-rose-950/80 text-rose-400 border border-rose-500/40 text-xs font-bold uppercase tracking-wider">
            <AlertTriangle className="w-3.5 h-3.5 text-rose-400 animate-bounce" />
            ERROR
          </span>
        )
      default:
        return (
          <span className="flex items-center gap-1.5 px-3 py-1 rounded bg-blue-950/80 text-blue-300 border border-blue-500/40 text-xs font-bold uppercase tracking-wider">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            {state || 'INITIALIZING'}
          </span>
        )
    }
  }

  return (
    <div className="space-y-4">
      {/* Top Header Card: Bot Selector & Environment Banner */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-lg backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-emerald-600/20 border border-emerald-500/40 rounded-xl text-emerald-400">
              <Bot className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-slate-100">AlgoTrading V2 — Paper Trading Bot</h2>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                  SIMULATION SANDBOX
                </span>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-slate-800 text-slate-300 border border-slate-700">
                  DRY_RUN
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Isolated 1-Minute event-driven execution with strict anti-lookahead matching and zero live broker access.
              </p>
            </div>
          </div>

          {/* Bot Session Selector & Actions */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-slate-400">Active Bot:</label>
              <select
                value={selectedSessionId}
                onChange={(e) => setSelectedSessionId(e.target.value)}
                className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono focus:outline-none focus:border-emerald-500"
              >
                {bots.length === 0 && <option value="">No bots available</option>}
                {bots.map((b) => (
                  <option key={b.session_id} value={b.session_id}>
                    {b.bot_name} ({b.bot_id}) — {b.lifecycle_state}
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold shadow-md shadow-emerald-600/20 transition-all"
            >
              <PlusCircle className="w-3.5 h-3.5" />
              New Bot
            </button>

            <button
              onClick={() => fetchBotDetail(selectedSessionId)}
              className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs border border-slate-700"
              title="Refresh State"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>

            {/* WebSocket Transport status */}
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-mono border ${
                wsConnected
                  ? 'bg-slate-950 text-emerald-400 border-emerald-900/60'
                  : 'bg-rose-950 text-rose-400 border-rose-900/60'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`} />
              {wsConnected ? 'WS STREAM ON' : 'WS OFFLINE'}
            </div>
          </div>
        </div>

        {errorMsg && (
          <div className="mt-3 p-2.5 bg-rose-950/80 border border-rose-800/80 rounded-lg text-rose-300 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0" />
              <span>{errorMsg}</span>
            </div>
            <button onClick={() => setErrorMsg(null)} className="text-rose-400 hover:text-rose-200">
              <XCircle className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {overview && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-3 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-4 flex-wrap">
            <span className="text-slate-400 font-mono">
              SUPERVISOR: <strong className={overview.status === 'HEALTHY' ? 'text-emerald-400' : 'text-amber-400'}>{overview.status}</strong>
            </span>
            <span className="text-slate-400 font-mono">
              ACTIVE BOTS: <strong className="text-slate-200">{overview.active_bots_count}</strong>
            </span>
            {overview.bot_counts_by_state && (
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800 text-[10px]">
                  {overview.bot_counts_by_state.RUNNING} RUNNING
                </span>
                <span className="px-2 py-0.5 rounded bg-amber-950/80 text-amber-400 border border-amber-800 text-[10px]">
                  {overview.bot_counts_by_state.PAUSED} PAUSED
                </span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 text-[10px]">
                  {overview.bot_counts_by_state.STOPPED} STOPPED
                </span>
                {overview.bot_counts_by_state.ERROR > 0 && (
                  <span className="px-2 py-0.5 rounded bg-rose-950/80 text-rose-400 border border-rose-800 text-[10px]">
                    {overview.bot_counts_by_state.ERROR} ERROR
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="text-[11px] text-slate-400 font-mono flex items-center gap-2 flex-wrap">
            <span className="px-2 py-0.5 rounded bg-slate-950 text-slate-400 border border-slate-800">
              DISPATCHER: {overview.dispatcher?.total_dispatched || 0} DISPATCHED
            </span>
            <span className="px-2 py-0.5 rounded bg-slate-950 text-emerald-400/80 border border-slate-800" title={overview.aggregate_simulation_capital?.disclaimer}>
              INDEPENDENT CAPITAL ONLY
            </span>
          </div>
        </div>
      )}

      {botSummary && (
        <>
          {/* Status & Control Card */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            {/* Overview / Lifecycle Banner */}
            <div className="lg:col-span-3 bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-sm flex flex-col justify-between">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3">
                    <span className="text-xl font-bold text-slate-100">{botSummary.bot_name}</span>
                    {getStatusBadge(botSummary.lifecycle_state)}
                  </div>
                  <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 mt-2 font-mono">
                    <span>ID: <strong className="text-slate-200">{botSummary.bot_id}</strong></span>
                    <span>Strategy: <strong className="text-blue-400">{botSummary.strategy_id} ({botSummary.strategy_version})</strong></span>
                    <span>Symbols: <strong className="text-slate-200">{botSummary.symbols.join(', ')}</strong></span>
                    <span>Timeframe: <strong className="text-emerald-400">{botSummary.timeframe}</strong></span>
                  </div>
                </div>

                {/* Control Action Buttons */}
                <div className="flex items-center gap-2">
                  {botSummary.lifecycle_state === 'STOPPED' && (
                    <button
                      onClick={() => handleLifecycleAction('start')}
                      disabled={actionLoading}
                      className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-all shadow-md shadow-emerald-600/20"
                    >
                      <Play className="w-3.5 h-3.5 fill-current" />
                      START BOT
                    </button>
                  )}

                  {botSummary.lifecycle_state === 'RUNNING' && (
                    <>
                      <button
                        onClick={() => handleLifecycleAction('pause')}
                        disabled={actionLoading}
                        className="flex items-center gap-1.5 px-3.5 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-all"
                      >
                        <Pause className="w-3.5 h-3.5 fill-current" />
                        PAUSE
                      </button>
                      <button
                        onClick={() => handleLifecycleAction('stop')}
                        disabled={actionLoading}
                        className="flex items-center gap-1.5 px-3.5 py-2 bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-all"
                      >
                        <Square className="w-3.5 h-3.5 fill-current" />
                        STOP
                      </button>
                    </>
                  )}

                  {botSummary.lifecycle_state === 'PAUSED' && (
                    <>
                      <button
                        onClick={() => handleLifecycleAction('resume')}
                        disabled={actionLoading}
                        className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-all shadow-md shadow-emerald-600/20"
                      >
                        <Play className="w-3.5 h-3.5 fill-current" />
                        RESUME
                      </button>
                      <button
                        onClick={() => handleLifecycleAction('stop')}
                        disabled={actionLoading}
                        className="flex items-center gap-1.5 px-3.5 py-2 bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-all"
                      >
                        <Square className="w-3.5 h-3.5 fill-current" />
                        STOP
                      </button>
                    </>
                  )}

                  {botSummary.lifecycle_state === 'ERROR' && (
                    <button
                      onClick={() => handleLifecycleAction('start')}
                      disabled={actionLoading}
                      className="flex items-center gap-1.5 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg text-xs font-bold"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      RESTART
                    </button>
                  )}
                </div>
              </div>

              {/* Security Boundary Reminder */}
              <div className="mt-3 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500 font-mono">
                <span>Config Hash: {botSummary.risk_config_hash ? botSummary.risk_config_hash.slice(0, 16) + '...' : 'DEFAULT'}</span>
                <span>Alpaca Gate: LOCKED (is_gate_open = False)</span>
              </div>
            </div>

            {/* Quick Metrics Tile */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-sm flex flex-col justify-between">
              <span className="text-xs font-semibold text-slate-400">Total Virtual Equity</span>
              <div className="my-1">
                <span className="text-2xl font-bold font-mono text-slate-100">
                  ${botSummary.current_equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
                <span
                  className={`ml-2 text-xs font-semibold font-mono ${
                    botSummary.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {botSummary.unrealized_pnl >= 0 ? '+' : ''}${botSummary.unrealized_pnl.toFixed(2)}
                </span>
              </div>
              <div className="text-[11px] text-slate-400 flex items-center justify-between font-mono pt-2 border-t border-slate-800">
                <span>Cash: ${botSummary.available_cash.toLocaleString('en-US', { maximumFractionDigits: 0 })}</span>
                <span>Positions: {botSummary.open_positions_count}</span>
              </div>
            </div>
          </div>

          {/* Navigation Sub-Tabs */}
          <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
            {[
              { id: 'portfolio', label: 'Simulation Portfolio', icon: Briefcase },
              { id: 'orders', label: 'Orders & Fills', icon: Layers },
              { id: 'performance', label: 'Performance Analytics', icon: TrendingUp },
              { id: 'health', label: 'Runtime Health & Logs', icon: Activity },
            ].map((tab) => {
              const Icon = tab.icon
              const active = activeSubTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveSubTab(tab.id as any)}
                  className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    active
                      ? 'bg-blue-600/20 text-blue-300 border border-blue-500/40'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {tab.label}
                </button>
              )
            })}
          </div>

          {/* Sub-Tab 1: Portfolio View */}
          {activeSubTab === 'portfolio' && portfolio && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5">
                  <span className="text-[11px] text-slate-400">Available Cash</span>
                  <p className="text-lg font-bold font-mono text-slate-100 mt-1">
                    ${portfolio.available_cash.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </p>
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5">
                  <span className="text-[11px] text-slate-400">Reserved Buying Power</span>
                  <p className="text-lg font-bold font-mono text-amber-400 mt-1">
                    ${portfolio.reserved_cash.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </p>
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5">
                  <span className="text-[11px] text-slate-400">Position Market Value</span>
                  <p className="text-lg font-bold font-mono text-slate-100 mt-1">
                    ${portfolio.market_value.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </p>
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5">
                  <span className="text-[11px] text-slate-400">Realized P&L</span>
                  <p className={`text-lg font-bold font-mono mt-1 ${portfolio.realized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    ${portfolio.realized_pnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </p>
                </div>
              </div>

              {/* Positions Table */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
                <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                    Simulated Open Positions ({portfolio.positions.length})
                  </h3>
                </div>
                {portfolio.positions.length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-500">
                    No active positions. Strategy is currently scanning for 1-minute entry signals.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] border-b border-slate-800">
                        <tr>
                          <th className="py-2.5 px-4">Symbol</th>
                          <th className="py-2.5 px-4">Quantity</th>
                          <th className="py-2.5 px-4">Avg Entry</th>
                          <th className="py-2.5 px-4">Current Price</th>
                          <th className="py-2.5 px-4">Market Value</th>
                          <th className="py-2.5 px-4">Unrealized P&L</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {portfolio.positions.map((p) => (
                          <tr key={p.symbol} className="hover:bg-slate-800/40">
                            <td className="py-2.5 px-4 font-bold text-slate-100">{p.symbol}</td>
                            <td className="py-2.5 px-4 text-slate-300">{p.qty}</td>
                            <td className="py-2.5 px-4 text-slate-300">${p.avg_entry_price.toFixed(2)}</td>
                            <td className="py-2.5 px-4 text-slate-300">${p.current_price.toFixed(2)}</td>
                            <td className="py-2.5 px-4 text-slate-300">${p.market_value.toFixed(2)}</td>
                            <td className={`py-2.5 px-4 font-bold ${p.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {p.unrealized_pnl >= 0 ? '+' : ''}${p.unrealized_pnl.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Sub-Tab 2: Orders & Fills View */}
          {activeSubTab === 'orders' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Orders */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
                <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                    Simulated Orders ({orders.length})
                  </h3>
                </div>
                {orders.length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-500">No simulated orders yet.</div>
                ) : (
                  <div className="overflow-x-auto max-h-[380px] overflow-y-auto">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] sticky top-0">
                        <tr>
                          <th className="py-2 px-3">Symbol</th>
                          <th className="py-2 px-3">Side</th>
                          <th className="py-2 px-3">Type</th>
                          <th className="py-2 px-3">Qty</th>
                          <th className="py-2 px-3">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {orders.map((o) => (
                          <tr key={o.simulated_order_id} className="hover:bg-slate-800/40">
                            <td className="py-2 px-3 font-bold text-slate-100">{o.symbol}</td>
                            <td className={`py-2 px-3 font-bold ${o.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>{o.side}</td>
                            <td className="py-2 px-3 text-slate-300">{o.order_type}</td>
                            <td className="py-2 px-3 text-slate-300">{o.quantity}</td>
                            <td className="py-2 px-3">
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300">
                                {o.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Fills */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
                <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                    Simulated Fills ({fills.length})
                  </h3>
                </div>
                {fills.length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-500">No execution fills recorded yet.</div>
                ) : (
                  <div className="overflow-x-auto max-h-[380px] overflow-y-auto">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] sticky top-0">
                        <tr>
                          <th className="py-2 px-3">Time</th>
                          <th className="py-2 px-3">Symbol</th>
                          <th className="py-2 px-3">Side</th>
                          <th className="py-2 px-3">Fill Price</th>
                          <th className="py-2 px-3">Qty</th>
                          <th className="py-2 px-3">Fee</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {fills.map((f) => (
                          <tr key={f.simulated_fill_id} className="hover:bg-slate-800/40">
                            <td className="py-2 px-3 text-slate-400">{new Date(f.fill_time).toLocaleTimeString()}</td>
                            <td className="py-2 px-3 font-bold text-slate-100">{f.symbol}</td>
                            <td className={`py-2 px-3 font-bold ${f.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>{f.side}</td>
                            <td className="py-2 px-3 text-slate-300">${f.fill_price.toFixed(2)}</td>
                            <td className="py-2 px-3 text-slate-300">{f.fill_qty}</td>
                            <td className="py-2 px-3 text-slate-400">${f.fee.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Sub-Tab 3: Performance Analytics */}
          {activeSubTab === 'performance' && performance && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5">
                  <span className="text-[11px] text-slate-400">Total Return</span>
                  <p className={`text-lg font-bold font-mono mt-1 ${(performance.pnl_metrics?.return_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {(performance.pnl_metrics?.return_pct ?? 0) >= 0 ? '+' : ''}{(performance.pnl_metrics?.return_pct ?? 0).toFixed(2)}%
                  </p>
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5">
                  <span className="text-[11px] text-slate-400">Total Orders Filled</span>
                  <p className="text-lg font-bold font-mono text-slate-100 mt-1">
                    {performance.order_metrics?.filled_orders ?? 0} / {performance.order_metrics?.total_orders ?? 0}
                  </p>
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5">
                  <span className="text-[11px] text-slate-400">Signals Acceptance Rate</span>
                  <p className="text-lg font-bold font-mono text-blue-400 mt-1">
                    {(performance.signals?.acceptance_rate_pct ?? (performance.signal_metrics ? (performance.signal_metrics.signals_accepted / Math.max(1, performance.signal_metrics.signals_received) * 100) : 0)).toFixed(1)}%
                  </p>
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5">
                  <span className="text-[11px] text-slate-400">Peak Drawdown</span>
                  <p className="text-lg font-bold font-mono text-amber-400 mt-1">
                    {(performance.drawdown_metrics?.current_drawdown_pct ?? 0).toFixed(2)}%
                  </p>
                </div>
              </div>

              {/* Conversion Funnel Box */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm">
                <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider mb-3">
                  Signal & Execution Conversion Funnel
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-center text-xs font-mono">
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-400">1. Signals Emitted</span>
                    <p className="text-xl font-bold text-slate-100 mt-1">{performance.signal_metrics?.signals_received ?? 0}</p>
                  </div>
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-400">2. Risk Accepted</span>
                    <p className="text-xl font-bold text-emerald-400 mt-1">{performance.signal_metrics?.signals_accepted ?? 0}</p>
                    <span className="text-[10px] text-slate-500">Rejected: {performance.signal_metrics?.signals_rejected ?? 0}</span>
                  </div>
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-400">3. Orders Filled</span>
                    <p className="text-xl font-bold text-blue-400 mt-1">{performance.order_metrics?.filled_orders ?? 0}</p>
                    <span className="text-[10px] text-slate-500">Fill Rate: {performance.order_metrics?.fill_rate_pct ?? 0}%</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Sub-Tab 4: Health & Event Logs */}
          {activeSubTab === 'health' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Health Metrics Column */}
              <div className="space-y-3">
                {health && (
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm space-y-3">
                    <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                      Runtime Health Diagnostics
                    </h3>
                    <div className="flex items-center justify-between text-xs py-1 border-b border-slate-800">
                      <span className="text-slate-400">Overall Status:</span>
                      <span className="font-bold text-emerald-400">{health.overall_status}</span>
                    </div>
                    <div className="flex items-center justify-between text-xs py-1 border-b border-slate-800">
                      <span className="text-slate-400">Consumer Feed:</span>
                      <span className={`font-bold ${health.consumer_health === 'HEALTHY' ? 'text-emerald-400' : 'text-amber-400'}`}>
                        {health.consumer_health}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs py-1 border-b border-slate-800">
                      <span className="text-slate-400">Processing Latency:</span>
                      <span className="font-mono text-slate-200">{(health.event_processing_latency_ms ?? 0).toFixed(1)} ms</span>
                    </div>
                    <div className="flex items-center justify-between text-xs py-1 border-b border-slate-800">
                      <span className="text-slate-400">Queue Depth:</span>
                      <span className="font-mono text-slate-200">{health.queue_depth} bars</span>
                    </div>
                    <div className="flex items-center justify-between text-xs py-1 border-b border-slate-800">
                      <span className="text-slate-400">Reconciliation:</span>
                      <span className="font-bold text-blue-400">{health.reconciliation_status}</span>
                    </div>
                    <div className="flex items-center justify-between text-xs py-1">
                      <span className="text-slate-400">Error Count:</span>
                      <span className={`font-bold ${health.error_count === 0 ? 'text-slate-200' : 'text-rose-400'}`}>
                        {health.error_count}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Real-time Activity Logs */}
              <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm flex flex-col h-[340px]">
                <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider mb-2">
                  Real-time Stream Activity Logs
                </h3>
                <div className="flex-1 overflow-y-auto space-y-1.5 font-mono text-[11px] bg-slate-950 p-3 rounded-lg border border-slate-800">
                  {eventLogs.length === 0 ? (
                    <span className="text-slate-500">Listening to WebSocket stream events...</span>
                  ) : (
                    eventLogs.map((log, idx) => (
                      <div key={idx} className="flex items-baseline gap-2">
                        <span className="text-slate-500">[{log.time}]</span>
                        <span className="text-emerald-400 font-bold">{log.type}</span>
                        <span className="text-slate-300 truncate">{log.details}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* Create Bot Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-5 shadow-2xl">
            <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
              <Bot className="w-5 h-5 text-emerald-400" />
              Configure & Initialize New Paper Bot
            </h3>
            <p className="text-xs text-slate-400 mt-1">
              Bot runs in an isolated Simulation sandbox. No real capital or Alpaca live execution.
            </p>

            <form onSubmit={handleCreateBot} className="space-y-3.5 mt-4">
              <div>
                <label className="text-xs font-medium text-slate-300">Bot ID</label>
                <input
                  type="text"
                  value={newBotId}
                  onChange={(e) => setNewBotId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono mt-1"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-medium text-slate-300">Bot Display Name</label>
                <input
                  type="text"
                  value={newBotName}
                  onChange={(e) => setNewBotName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 mt-1"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-slate-300">Symbols (comma separated)</label>
                  <input
                    type="text"
                    value={newSymbols}
                    onChange={(e) => setNewSymbols(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono mt-1"
                    required
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-300">Initial Virtual Cash ($)</label>
                  <input
                    type="number"
                    value={newInitialCash}
                    onChange={(e) => setNewInitialCash(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono mt-1"
                    min={1000}
                    step={1000}
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-slate-300">Strategy</label>
                  <select
                    value={newStrategy}
                    onChange={(e) => setNewStrategy(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono mt-1"
                  >
                    <option value="MA_CROSS_1M">MA Crossover 1m (SMA-20/50)</option>
                    <option value="RSI_1M">RSI Mean Reversion (14)</option>
                    <option value="V1_FLINK_ADAPTER">V1 Flink Strategy Adapter</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-300">Stop Policy</label>
                  <select
                    value={newStopPolicy}
                    onChange={(e) => setNewStopPolicy(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono mt-1"
                  >
                    <option value="CANCEL_REMAINDER">CANCEL_REMAINDER (Safe)</option>
                    <option value="KEEP_WORKING">KEEP_WORKING</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold shadow-md shadow-emerald-600/20"
                >
                  {actionLoading ? 'Creating...' : 'Initialize Bot'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default PaperBotPanel
