import React, { useState, useEffect, useCallback } from 'react'
import {
  Briefcase,
  Clock,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Filter,
  Eye,
  Sliders,
  Trash2,
  RotateCcw,
  Shield,
  Layers,
  Zap,
  Info,
  Lock
} from 'lucide-react'
import type {
  WorkbenchAccount,
  WorkbenchPosition,
  WorkbenchOrder,
  WorkbenchActivity
} from '../types'

interface TradingWorkbenchPanelProps {
  apiBase?: string
}

export const TradingWorkbenchPanel: React.FC<TradingWorkbenchPanelProps> = ({
  apiBase = 'http://127.0.0.1:8005'
}) => {
  // Data source toggle: 'mock' | 'alpaca_paper'
  const [dataSource, setDataSource] = useState<'mock' | 'alpaca_paper'>('mock')

  // Navigation sub-tab
  const [subTab, setSubTab] = useState<'open_orders' | 'order_history' | 'positions' | 'activity'>('open_orders')

  // Data states
  const [account, setAccount] = useState<WorkbenchAccount | null>(null)
  const [positions, setPositions] = useState<WorkbenchPosition[]>([])
  const [orders, setOrders] = useState<WorkbenchOrder[]>([])
  const [activities, setActivities] = useState<WorkbenchActivity[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<string>('')

  // Order Ticket Form State
  const [symbol, setSymbol] = useState('NVDA')
  const [side, setSide] = useState<'buy' | 'sell'>('buy')
  const [orderType, setOrderType] = useState<'market' | 'limit' | 'stop' | 'stop_limit' | 'trailing_stop'>('market')
  const [sizeMode, setSizeMode] = useState<'qty' | 'notional'>('qty')
  const [qty, setQty] = useState('10')
  const [notional, setNotional] = useState('1000')
  const [limitPrice, setLimitPrice] = useState('')
  const [stopPrice, setStopPrice] = useState('')
  const [trailPrice, setTrailPrice] = useState('')
  const [trailPercent, setTrailPercent] = useState('')
  const [timeInForce, setTimeInForce] = useState<'day' | 'gtc' | 'ioc' | 'fok'>('day')
  const [ticketError, setTicketError] = useState<string | null>(null)
  const [ticketSuccess, setTicketSuccess] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Filter state
  const [symbolFilter, setSymbolFilter] = useState('')
  const [sideFilter, setSideFilter] = useState<'all' | 'buy' | 'sell'>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | 'filled' | 'canceled' | 'replaced' | 'new'>('all')

  // Selected Order for Details Modal
  const [selectedOrder, setSelectedOrder] = useState<WorkbenchOrder | null>(null)
  const [selectedOrderActivities, setSelectedOrderActivities] = useState<WorkbenchActivity[]>([])

  // Replace Order Modal State
  const [replacingOrder, setReplacingOrder] = useState<WorkbenchOrder | null>(null)
  const [replaceQty, setReplaceQty] = useState('')
  const [replaceLimitPrice, setReplaceLimitPrice] = useState('')
  const [replaceStopPrice, setReplaceStopPrice] = useState('')
  const [replaceSubmitting, setReplaceSubmitting] = useState(false)

  // Fetch all workbench data
  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const [accRes, posRes, ordRes, actRes] = await Promise.all([
        fetch(`${apiBase}/api/workbench/account?source=${dataSource}`),
        fetch(`${apiBase}/api/workbench/positions?source=${dataSource}`),
        fetch(`${apiBase}/api/workbench/orders?limit=100&source=${dataSource}`),
        fetch(`${apiBase}/api/workbench/activities?limit=100`),
      ])

      if (!accRes.ok || !posRes.ok || !ordRes.ok || !actRes.ok) {
        throw new Error('Failed to retrieve simulation data from backend.')
      }

      const accData = await accRes.json()
      const posData = await posRes.json()
      const ordData = await ordRes.json()
      const actData = await actRes.json()

      setAccount(accData)
      setPositions(posData)
      setOrders(ordData)
      setActivities(actData)
      setLastUpdated(new Date().toLocaleTimeString())
    } catch (err: any) {
      setError(err.message || 'Connection error with simulation backend.')
    } finally {
      setLoading(false)
    }
  }, [apiBase, dataSource])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 8000)
    return () => clearInterval(interval)
  }, [fetchData])

  // Submit Order Ticket
  const handleSubmitOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    setTicketError(null)
    setTicketSuccess(null)

    // Basic validation
    if (!symbol.trim()) {
      setTicketError('Symbol ticker is required.')
      return
    }

    const payload: Record<string, any> = {
      symbol: symbol.trim().toUpperCase(),
      side,
      type: orderType,
      time_in_force: timeInForce,
    }

    if (sizeMode === 'qty') {
      const q = parseFloat(qty)
      if (isNaN(q) || q <= 0) {
        setTicketError('Quantity must be greater than 0.')
        return
      }
      payload.qty = q
    } else {
      const n = parseFloat(notional)
      if (isNaN(n) || n <= 0) {
        setTicketError('Notional value must be greater than 0.')
        return
      }
      payload.notional = n
    }

    if (orderType === 'limit' || orderType === 'stop_limit') {
      const lp = parseFloat(limitPrice)
      if (isNaN(lp) || lp <= 0) {
        setTicketError('Limit price must be greater than 0.')
        return
      }
      payload.limit_price = lp
    }

    if (orderType === 'stop' || orderType === 'stop_limit') {
      const sp = parseFloat(stopPrice)
      if (isNaN(sp) || sp <= 0) {
        setTicketError('Stop price must be greater than 0.')
        return
      }
      payload.stop_price = sp
    }

    if (orderType === 'trailing_stop') {
      if (trailPercent) {
        const tp = parseFloat(trailPercent)
        if (isNaN(tp) || tp <= 0 || tp > 100) {
          setTicketError('Trail percent must be between 0 and 100.')
          return
        }
        payload.trail_percent = tp
      } else if (trailPrice) {
        const tpr = parseFloat(trailPrice)
        if (isNaN(tpr) || tpr <= 0) {
          setTicketError('Trail price must be greater than 0.')
          return
        }
        payload.trail_price = tpr
      } else {
        setTicketError('Trailing stop orders require either Trail % or Trail $.')
        return
      }
    }

    try {
      setSubmitting(true)
      const res = await fetch(`${apiBase}/api/workbench/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Order rejected by simulation engine.')
      }

      setTicketSuccess(`Simulated order submitted: ${data.id} (${data.status.toUpperCase()})`)
      fetchData()
    } catch (err: any) {
      setTicketError(err.message || 'Error submitting simulated order.')
    } finally {
      setSubmitting(false)
    }
  }

  // Cancel single order
  const handleCancelOrder = async (orderId: string) => {
    try {
      const res = await fetch(`${apiBase}/api/workbench/orders/${orderId}`, {
        method: 'DELETE',
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Cancel failed')
      }
      fetchData()
      if (selectedOrder && selectedOrder.id === orderId) {
        setSelectedOrder(null)
      }
    } catch (err: any) {
      alert(`Error canceling order: ${err.message}`)
    }
  }

  // Cancel all open orders
  const handleCancelAll = async () => {
    if (!window.confirm('Cancel all currently open simulated orders?')) return
    try {
      const res = await fetch(`${apiBase}/api/workbench/orders`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Bulk cancel failed')
      fetchData()
    } catch (err: any) {
      alert(`Error: ${err.message}`)
    }
  }

  // Reset simulation account
  const handleResetAccount = async () => {
    if (!window.confirm('Reset simulated account back to $100,000 cash and wipe all mock positions?')) return
    try {
      const res = await fetch(`${apiBase}/api/workbench/reset`, { method: 'POST' })
      if (!res.ok) throw new Error('Reset failed')
      fetchData()
    } catch (err: any) {
      alert(`Error: ${err.message}`)
    }
  }

  // Open Order Details
  const handleInspectOrder = async (order: WorkbenchOrder) => {
    setSelectedOrder(order)
    try {
      const res = await fetch(`${apiBase}/api/workbench/orders/${order.id}`)
      if (res.ok) {
        const data = await res.json()
        setSelectedOrderActivities(data.activities || [])
      }
    } catch {
      setSelectedOrderActivities([])
    }
  }

  // Open Replace Modal
  const handleOpenReplace = (order: WorkbenchOrder) => {
    setReplacingOrder(order)
    setReplaceQty(order.qty ? String(order.qty) : '')
    setReplaceLimitPrice(order.limit_price ? String(order.limit_price) : '')
    setReplaceStopPrice(order.stop_price ? String(order.stop_price) : '')
  }

  // Submit Replace Order
  const handleConfirmReplace = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!replacingOrder) return
    try {
      setReplaceSubmitting(true)
      const payload: Record<string, any> = {}
      if (replaceQty) payload.qty = parseFloat(replaceQty)
      if (replaceLimitPrice) payload.limit_price = parseFloat(replaceLimitPrice)
      if (replaceStopPrice) payload.stop_price = parseFloat(replaceStopPrice)

      const res = await fetch(`${apiBase}/api/workbench/orders/${replacingOrder.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Replace failed')

      setReplacingOrder(null)
      fetchData()
    } catch (err: any) {
      alert(`Error replacing order: ${err.message}`)
    } finally {
      setReplaceSubmitting(false)
    }
  }

  // Filtered orders list
  const openOrders = orders.filter((o) => ['new', 'accepted', 'pending_new', 'partially_filled'].includes(o.status))
  const closedOrders = orders.filter((o) => ['filled', 'canceled', 'rejected', 'expired', 'replaced'].includes(o.status))

  const filterOrders = (list: WorkbenchOrder[]) => {
    return list.filter((o) => {
      if (symbolFilter && !o.symbol.toLowerCase().includes(symbolFilter.toLowerCase())) return false
      if (sideFilter !== 'all' && o.side.toLowerCase() !== sideFilter) return false
      if (statusFilter !== 'all' && o.status.toLowerCase() !== statusFilter) return false
      return true
    })
  }

  const filteredOpenOrders = filterOrders(openOrders)
  const filteredClosedOrders = filterOrders(closedOrders)

  return (
    <div className="flex flex-col gap-4 font-sans text-slate-100">
      {/* 1. Header Banner & Account Overview Strip */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg border ${
              dataSource === 'mock'
                ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                : 'bg-sky-500/10 border-sky-500/30 text-sky-400'
            }`}>
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold tracking-wide text-slate-100">ORDER MANAGEMENT & TRADING WORKBENCH</h2>
                <span className={`text-[11px] px-2 py-0.5 rounded-full font-mono font-semibold flex items-center gap-1 border ${
                  dataSource === 'mock'
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                    : 'bg-sky-500/20 text-sky-300 border-sky-500/40'
                }`}>
                  <Shield className="w-3 h-3" />
                  {dataSource === 'mock' ? 'SIMULATED MOCK BROKER' : 'ALPACA PAPER (READ-ONLY SYNC)'}
                </span>
                {dataSource === 'alpaca_paper' && (
                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 font-mono font-semibold flex items-center gap-1">
                    <Lock className="w-3 h-3" />
                    EXECUTION GATE: LOCKED
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400">
                {dataSource === 'mock'
                  ? 'Alpaca Paper Trading Guide Simulation Engine • Isolated from Live Broker • Safe Sandbox'
                  : 'Live Read-Only Synchronization with Alpaca Paper API • Fail-Closed Execution Gate'
                }
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Source Switcher Toggle */}
            <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
              <button
                type="button"
                onClick={() => setDataSource('mock')}
                className={`px-3 py-1 rounded-md font-medium transition flex items-center gap-1.5 ${
                  dataSource === 'mock'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Shield className="w-3 h-3" />
                MOCK BROKER
              </button>
              <button
                type="button"
                onClick={() => setDataSource('alpaca_paper')}
                className={`px-3 py-1 rounded-md font-medium transition flex items-center gap-1.5 ${
                  dataSource === 'alpaca_paper'
                    ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Lock className="w-3 h-3" />
                ALPACA PAPER
              </button>
            </div>

            <button
              onClick={fetchData}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-300 border border-slate-700 transition"
              title="Refresh Workbench Data"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
            {dataSource === 'mock' && (
              <button
                onClick={handleResetAccount}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-950/60 hover:bg-rose-900/60 text-xs font-medium text-rose-300 border border-rose-800/60 transition"
                title="Reset Mock Portfolio to $100,000"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset Account
              </button>
            )}
          </div>
        </div>

        {/* Account Stat Cards */}
        {account && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3">
            <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800/80">
              <span className="text-[11px] text-slate-400 uppercase tracking-wider block font-mono">Portfolio Value</span>
              <span className="text-lg font-bold font-mono text-emerald-400">
                ${account.portfolio_value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
            <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800/80">
              <span className="text-[11px] text-slate-400 uppercase tracking-wider block font-mono">Cash Available</span>
              <span className="text-lg font-bold font-mono text-slate-100">
                ${account.cash.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
            <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800/80">
              <span className="text-[11px] text-slate-400 uppercase tracking-wider block font-mono">Buying Power (4x)</span>
              <span className="text-lg font-bold font-mono text-blue-400">
                ${account.buying_power.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
            <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800/80">
              <span className="text-[11px] text-slate-400 uppercase tracking-wider block font-mono">Account / Status</span>
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold font-mono text-slate-200">{account.account_number}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono">
                  {account.status}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="p-3 bg-rose-950/80 border border-rose-800 text-rose-300 rounded-lg text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400" />
            <span>{error}</span>
          </div>
          <button onClick={fetchData} className="underline text-xs">Retry</button>
        </div>
      )}

      {/* 2. Main Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left Column: Order Ticket (4 cols) */}
        <div className="lg:col-span-4 bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg flex flex-col gap-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <h3 className="text-sm font-bold tracking-wider text-slate-200 flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-400" />
              {dataSource === 'mock' ? 'SIMULATED ORDER TICKET' : 'PAPER ORDER TICKET (LOCKED)'}
            </h3>
            <span className={`text-[10px] px-2 py-0.5 rounded font-mono ${
              dataSource === 'mock' ? 'bg-slate-800 text-slate-400' : 'bg-rose-950 text-rose-300 border border-rose-800/60'
            }`}>
              {dataSource === 'mock' ? 'MOCK' : 'GATE LOCKED'}
            </span>
          </div>

          {dataSource === 'alpaca_paper' && (
            <div className="p-3 bg-sky-950/40 border border-sky-800/60 rounded-lg text-sky-300 text-xs flex items-center gap-2">
              <Lock className="w-4 h-4 text-amber-400 shrink-0" />
              <span>
                <strong>Alpaca Paper (Read-Only):</strong> Live broker synchronization active. Direct order placement is locked by the Paper Execution Gate. Toggle to <strong>MOCK BROKER</strong> above to submit simulated orders.
              </span>
            </div>
          )}

          <form onSubmit={handleSubmitOrder} className="flex flex-col gap-3 text-xs">
            {/* Symbol Selection */}
            <div>
              <label className="text-slate-400 mb-1 block font-medium">Symbol</label>
              <div className="flex gap-1.5 mb-2">
                {['NVDA', 'AAPL', 'TSLA', 'BTC/USD', 'ETH/USD'].map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSymbol(s)}
                    className={`px-2 py-1 rounded text-[11px] font-bold border transition ${
                      symbol === s
                        ? 'bg-blue-600 text-white border-blue-400'
                        : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
              <input
                type="text"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                placeholder="e.g. MSFT, BTC/USD"
                className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-100 font-mono focus:outline-none focus:border-blue-500"
              />
            </div>

            {/* Side Selection: BUY vs SELL */}
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setSide('buy')}
                className={`py-2 rounded-lg font-bold text-xs uppercase tracking-wider transition border ${
                  side === 'buy'
                    ? 'bg-emerald-600 text-white border-emerald-400 shadow-md shadow-emerald-600/30'
                    : 'bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-700'
                }`}
              >
                Buy (Long)
              </button>
              <button
                type="button"
                onClick={() => setSide('sell')}
                className={`py-2 rounded-lg font-bold text-xs uppercase tracking-wider transition border ${
                  side === 'sell'
                    ? 'bg-rose-600 text-white border-rose-400 shadow-md shadow-rose-600/30'
                    : 'bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-700'
                }`}
              >
                Sell (Short)
              </button>
            </div>

            {/* Order Type & TIF */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-slate-400 mb-1 block font-medium">Order Type</label>
                <select
                  value={orderType}
                  onChange={(e) => setOrderType(e.target.value as any)}
                  className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-100 font-mono focus:outline-none focus:border-blue-500"
                >
                  <option value="market">Market</option>
                  <option value="limit">Limit</option>
                  <option value="stop">Stop</option>
                  <option value="stop_limit">Stop Limit</option>
                  <option value="trailing_stop">Trailing Stop</option>
                </select>
              </div>

              <div>
                <label className="text-slate-400 mb-1 block font-medium">Time In Force</label>
                <select
                  value={timeInForce}
                  onChange={(e) => setTimeInForce(e.target.value as any)}
                  className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-100 font-mono focus:outline-none focus:border-blue-500"
                >
                  <option value="day">DAY</option>
                  <option value="gtc">GTC</option>
                  <option value="ioc">IOC</option>
                  <option value="fok">FOK</option>
                </select>
              </div>
            </div>

            {/* Sizing Mode: Quantity vs Notional */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-slate-400 font-medium">Order Sizing</label>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setSizeMode('qty')}
                    className={`text-[10px] px-1.5 py-0.5 rounded ${sizeMode === 'qty' ? 'bg-blue-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
                  >
                    Units / Shares
                  </button>
                  <button
                    type="button"
                    onClick={() => setSizeMode('notional')}
                    className={`text-[10px] px-1.5 py-0.5 rounded ${sizeMode === 'notional' ? 'bg-blue-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
                  >
                    Notional ($)
                  </button>
                </div>
              </div>

              {sizeMode === 'qty' ? (
                <input
                  type="number"
                  step="any"
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                  placeholder="e.g. 10 or 0.05"
                  className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-100 font-mono focus:outline-none focus:border-blue-500"
                />
              ) : (
                <input
                  type="number"
                  step="any"
                  value={notional}
                  onChange={(e) => setNotional(e.target.value)}
                  placeholder="e.g. 500.00"
                  className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-100 font-mono focus:outline-none focus:border-blue-500"
                />
              )}
            </div>

            {/* Conditional Price Inputs */}
            {(orderType === 'limit' || orderType === 'stop_limit') && (
              <div>
                <label className="text-slate-400 mb-1 block font-medium">Limit Price ($)</label>
                <input
                  type="number"
                  step="any"
                  value={limitPrice}
                  onChange={(e) => setLimitPrice(e.target.value)}
                  placeholder="e.g. 135.50"
                  className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-100 font-mono focus:outline-none focus:border-blue-500"
                />
              </div>
            )}

            {(orderType === 'stop' || orderType === 'stop_limit') && (
              <div>
                <label className="text-slate-400 mb-1 block font-medium">Stop Price ($)</label>
                <input
                  type="number"
                  step="any"
                  value={stopPrice}
                  onChange={(e) => setStopPrice(e.target.value)}
                  placeholder="e.g. 130.00"
                  className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-100 font-mono focus:outline-none focus:border-blue-500"
                />
              </div>
            )}

            {orderType === 'trailing_stop' && (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-slate-400 mb-1 block font-medium">Trail %</label>
                  <input
                    type="number"
                    step="any"
                    value={trailPercent}
                    onChange={(e) => setTrailPercent(e.target.value)}
                    placeholder="e.g. 2.5"
                    className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-100 font-mono focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="text-slate-400 mb-1 block font-medium">Trail Price ($)</label>
                  <input
                    type="number"
                    step="any"
                    value={trailPrice}
                    onChange={(e) => setTrailPrice(e.target.value)}
                    placeholder="e.g. 5.00"
                    className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-100 font-mono focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>
            )}

            {ticketError && (
              <div className="p-2.5 bg-rose-950/70 border border-rose-800 text-rose-300 rounded text-xs flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 text-rose-400" />
                <span>{ticketError}</span>
              </div>
            )}

            {ticketSuccess && (
              <div className="p-2.5 bg-emerald-950/70 border border-emerald-800 text-emerald-300 rounded text-xs flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0 text-emerald-400" />
                <span>{ticketSuccess}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || dataSource === 'alpaca_paper'}
              className={`w-full py-2.5 rounded-lg font-bold text-xs uppercase tracking-wider transition mt-1 shadow-md ${
                dataSource === 'alpaca_paper'
                  ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                  : side === 'buy'
                  ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/30'
                  : 'bg-rose-600 hover:bg-rose-500 text-white shadow-rose-600/30'
              }`}
            >
              {dataSource === 'alpaca_paper'
                ? 'Execution Gate Locked (Read-Only)'
                : submitting
                ? 'Submitting...'
                : `Submit Simulated ${side.toUpperCase()} Order`
              }
            </button>

            <p className="text-[10px] text-slate-400 text-center font-mono mt-1">
              {dataSource === 'alpaca_paper'
                ? 'Alpaca Paper Gate Enforced • Zero Network Mutation'
                : 'Protected by Server-Side Guard • Zero Broker Mutation'
              }
            </p>
          </form>
        </div>

        {/* Right Column: Order Management & Activity Tabs (8 cols) */}
        <div className="lg:col-span-8 bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg flex flex-col gap-3">
          {/* Sub-Tabs & Actions Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-2.5">
            <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
              <button
                onClick={() => setSubTab('open_orders')}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold transition flex items-center gap-1.5 ${
                  subTab === 'open_orders'
                    ? 'bg-blue-600 text-white shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>Open Orders</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-800 text-blue-300 font-mono">
                  {openOrders.length}
                </span>
              </button>

              <button
                onClick={() => setSubTab('order_history')}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold transition flex items-center gap-1.5 ${
                  subTab === 'order_history'
                    ? 'bg-blue-600 text-white shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>Order History</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-300 font-mono">
                  {closedOrders.length}
                </span>
              </button>

              <button
                onClick={() => setSubTab('positions')}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold transition flex items-center gap-1.5 ${
                  subTab === 'positions'
                    ? 'bg-blue-600 text-white shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>Positions</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-300 font-mono">
                  {positions.length}
                </span>
              </button>

              <button
                onClick={() => setSubTab('activity')}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold transition flex items-center gap-1.5 ${
                  subTab === 'activity'
                    ? 'bg-blue-600 text-white shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>Order Activity</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-300 font-mono">
                  {activities.length}
                </span>
              </button>
            </div>

            {subTab === 'open_orders' && openOrders.length > 0 && (
              <button
                onClick={handleCancelAll}
                className="flex items-center gap-1 px-2.5 py-1 rounded bg-rose-950/60 hover:bg-rose-900 text-rose-300 border border-rose-800 text-xs font-medium transition"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Cancel All
              </button>
            )}
          </div>

          {/* Filtering Controls (for Orders and History) */}
          {(subTab === 'open_orders' || subTab === 'order_history') && (
            <div className="flex flex-wrap items-center gap-2 bg-slate-950/50 p-2 rounded-lg border border-slate-800/80 text-xs">
              <div className="flex items-center gap-1.5">
                <Filter className="w-3.5 h-3.5 text-slate-400" />
                <span className="text-slate-400 font-medium">Filter:</span>
              </div>
              <input
                type="text"
                placeholder="Symbol (e.g. NVDA)"
                value={symbolFilter}
                onChange={(e) => setSymbolFilter(e.target.value)}
                className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 font-mono text-xs w-32 focus:outline-none focus:border-blue-500"
              />
              <select
                value={sideFilter}
                onChange={(e) => setSideFilter(e.target.value as any)}
                className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-xs focus:outline-none focus:border-blue-500"
              >
                <option value="all">All Sides</option>
                <option value="buy">Buy Only</option>
                <option value="sell">Sell Only</option>
              </select>

              {subTab === 'order_history' && (
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as any)}
                  className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 text-xs focus:outline-none focus:border-blue-500"
                >
                  <option value="all">All Statuses</option>
                  <option value="filled">Filled</option>
                  <option value="canceled">Canceled</option>
                  <option value="replaced">Replaced</option>
                </select>
              )}

              {(symbolFilter || sideFilter !== 'all' || statusFilter !== 'all') && (
                <button
                  onClick={() => {
                    setSymbolFilter('')
                    setSideFilter('all')
                    setStatusFilter('all')
                  }}
                  className="text-xs text-blue-400 hover:underline ml-auto"
                >
                  Clear Filters
                </button>
              )}
            </div>
          )}

          {/* Sub-Tab 1: Open Orders Table */}
          {subTab === 'open_orders' && (
            <div className="overflow-x-auto min-h-[300px]">
              {filteredOpenOrders.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 text-slate-400 text-xs gap-2">
                  <Clock className="w-8 h-8 text-slate-600" />
                  <span>No open simulated orders matching filters.</span>
                  <span className="text-[11px] text-slate-400">Place an order using the Order Ticket on the left.</span>
                </div>
              ) : (
                <table className="w-full text-left text-xs border-collapse font-mono">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/40">
                      <th className="py-2 px-3">Symbol</th>
                      <th className="py-2 px-3">Side</th>
                      <th className="py-2 px-3">Type</th>
                      <th className="py-2 px-3">Qty</th>
                      <th className="py-2 px-3">Price</th>
                      <th className="py-2 px-3">Status</th>
                      <th className="py-2 px-3">Submitted</th>
                      <th className="py-2 px-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredOpenOrders.map((o) => (
                      <tr key={o.id} className="border-b border-slate-800/60 hover:bg-slate-800/30 transition">
                        <td className="py-2 px-3 font-bold text-slate-100">{o.symbol}</td>
                        <td className="py-2 px-3">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${o.side === 'buy' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                            {o.side.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-slate-300 uppercase text-[11px]">{o.type}</td>
                        <td className="py-2 px-3 text-slate-200">{o.qty ?? '-'}</td>
                        <td className="py-2 px-3 text-slate-300">
                          {o.limit_price ? `$${o.limit_price.toFixed(2)}` : o.stop_price ? `Stop $${o.stop_price.toFixed(2)}` : 'MKT'}
                        </td>
                        <td className="py-2 px-3">
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-500/20 text-blue-300 font-semibold">
                            {o.status.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-slate-400 text-[11px]">{new Date(o.submitted_at).toLocaleTimeString()}</td>
                        <td className="py-2 px-3 text-right space-x-1.5">
                          <button
                            onClick={() => handleOpenReplace(o)}
                            className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[11px]"
                            title="Replace order"
                          >
                            Replace
                          </button>
                          <button
                            onClick={() => handleCancelOrder(o.id)}
                            className="px-2 py-0.5 rounded bg-rose-950/60 hover:bg-rose-900 text-rose-300 border border-rose-800 text-[11px]"
                            title="Cancel order"
                          >
                            Cancel
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* Sub-Tab 2: Order History Table */}
          {subTab === 'order_history' && (
            <div className="overflow-x-auto min-h-[300px]">
              {filteredClosedOrders.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 text-slate-400 text-xs gap-2">
                  <CheckCircle2 className="w-8 h-8 text-slate-600" />
                  <span>No completed orders in simulation history.</span>
                </div>
              ) : (
                <table className="w-full text-left text-xs border-collapse font-mono">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/40">
                      <th className="py-2 px-3">Symbol</th>
                      <th className="py-2 px-3">Side</th>
                      <th className="py-2 px-3">Type</th>
                      <th className="py-2 px-3">Filled Qty</th>
                      <th className="py-2 px-3">Avg Price</th>
                      <th className="py-2 px-3">Status</th>
                      <th className="py-2 px-3">Time</th>
                      <th className="py-2 px-3 text-right">Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredClosedOrders.map((o) => (
                      <tr key={o.id} className="border-b border-slate-800/60 hover:bg-slate-800/30 transition">
                        <td className="py-2 px-3 font-bold text-slate-100">{o.symbol}</td>
                        <td className="py-2 px-3">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${o.side === 'buy' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                            {o.side.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-slate-300 uppercase text-[11px]">{o.type}</td>
                        <td className="py-2 px-3 text-slate-200">{o.filled_qty}</td>
                        <td className="py-2 px-3 text-slate-300">{o.filled_avg_price ? `$${o.filled_avg_price.toFixed(2)}` : '-'}</td>
                        <td className="py-2 px-3">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                            o.status === 'filled' ? 'bg-emerald-500/20 text-emerald-300' :
                            o.status === 'canceled' ? 'bg-rose-500/20 text-rose-300' :
                            'bg-slate-700 text-slate-300'
                          }`}>
                            {o.status.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-slate-400 text-[11px]">{new Date(o.updated_at).toLocaleTimeString()}</td>
                        <td className="py-2 px-3 text-right">
                          <button
                            onClick={() => handleInspectOrder(o)}
                            className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
                            title="Inspect order lifecycle details"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* Sub-Tab 3: Positions Table */}
          {subTab === 'positions' && (
            <div className="overflow-x-auto min-h-[300px]">
              {positions.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 text-slate-400 text-xs gap-2">
                  <Briefcase className="w-8 h-8 text-slate-600" />
                  <span>No open simulated positions.</span>
                  <span className="text-[11px] text-slate-400">Buy simulated assets to create positions.</span>
                </div>
              ) : (
                <table className="w-full text-left text-xs border-collapse font-mono">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/40">
                      <th className="py-2 px-3">Symbol</th>
                      <th className="py-2 px-3">Qty</th>
                      <th className="py-2 px-3">Avg Entry</th>
                      <th className="py-2 px-3">Current Price</th>
                      <th className="py-2 px-3">Market Value</th>
                      <th className="py-2 px-3 text-right">Unrealized P/L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((p) => {
                      const isPos = p.unrealized_pl >= 0
                      return (
                        <tr key={p.symbol} className="border-b border-slate-800/60 hover:bg-slate-800/30 transition">
                          <td className="py-2 px-3 font-bold text-slate-100 flex items-center gap-1.5">
                            <span>{p.symbol}</span>
                            <span className="text-[9px] px-1 py-0.2 rounded bg-slate-800 text-slate-400">{p.asset_class}</span>
                          </td>
                          <td className="py-2 px-3 text-slate-200">{p.qty}</td>
                          <td className="py-2 px-3 text-slate-300">${p.avg_entry_price.toFixed(2)}</td>
                          <td className="py-2 px-3 text-slate-300">${p.current_price.toFixed(2)}</td>
                          <td className="py-2 px-3 text-slate-200">${p.market_value.toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                          <td className={`py-2 px-3 text-right font-bold ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {isPos ? '+' : ''}${p.unrealized_pl.toFixed(2)} ({isPos ? '+' : ''}{p.unrealized_plpc.toFixed(2)}%)
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* Sub-Tab 4: Order Activity Log */}
          {subTab === 'activity' && (
            <div className="overflow-x-auto min-h-[300px]">
              {activities.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 text-slate-400 text-xs gap-2">
                  <Layers className="w-8 h-8 text-slate-600" />
                  <span>No order activities recorded yet.</span>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  {activities.map((a) => (
                    <div
                      key={a.id}
                      className="p-2.5 bg-slate-950/60 border border-slate-800/80 rounded-lg flex items-start justify-between text-xs font-mono"
                    >
                      <div className="flex items-start gap-2.5">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold mt-0.5 ${
                          a.activity_type === 'FILLED' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' :
                          a.activity_type === 'CANCELED' ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' :
                          a.activity_type === 'REPLACED' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' :
                          'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                        }`}>
                          {a.activity_type}
                        </span>
                        <div>
                          <p className="text-slate-200 font-sans">{a.description}</p>
                          <p className="text-[10px] text-slate-400 mt-0.5">Order ID: {a.order_id}</p>
                        </div>
                      </div>
                      <span className="text-[10px] text-slate-400 flex-shrink-0">
                        {new Date(a.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="flex items-center justify-between text-[11px] text-slate-400 border-t border-slate-800 pt-2 font-mono">
            <span>Simulated Workbench Environment</span>
            <span>Last Updated: {lastUpdated || 'Connecting...'}</span>
          </div>
        </div>
      </div>

      {/* 3. Modal: Order Details & Activity Inspection */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-lg w-full p-5 shadow-2xl flex flex-col gap-4 max-h-[90vh] overflow-y-auto font-mono text-xs">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Info className="w-4 h-4 text-blue-400" />
                <h3 className="text-sm font-bold text-slate-100 font-sans">Simulated Order Details</h3>
              </div>
              <button
                onClick={() => setSelectedOrder(null)}
                className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200"
              >
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2.5 bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div>
                <span className="text-slate-400 text-[10px] block">Order ID</span>
                <span className="text-slate-200 font-semibold">{selectedOrder.id}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] block">Client Order ID</span>
                <span className="text-slate-200">{selectedOrder.client_order_id}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] block">Symbol / Asset</span>
                <span className="text-slate-200 font-bold">{selectedOrder.symbol} ({selectedOrder.asset_class})</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] block">Side / Type</span>
                <span className="text-slate-200 uppercase">{selectedOrder.side} {selectedOrder.type}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] block">Quantity / Filled</span>
                <span className="text-slate-200">{selectedOrder.filled_qty} / {selectedOrder.qty ?? 'N/A'}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] block">Avg Fill Price</span>
                <span className="text-slate-200 font-bold">{selectedOrder.filled_avg_price ? `$${selectedOrder.filled_avg_price.toFixed(2)}` : 'N/A'}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] block">Time In Force</span>
                <span className="text-slate-200 uppercase">{selectedOrder.time_in_force}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] block">Current Status</span>
                <span className="text-emerald-400 font-bold uppercase">{selectedOrder.status}</span>
              </div>
            </div>

            {/* Lifecycle Activities */}
            <div>
              <h4 className="text-xs font-bold text-slate-300 font-sans mb-2 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                Order Lifecycle Timeline
              </h4>
              <div className="flex flex-col gap-1.5 max-h-40 overflow-y-auto">
                {selectedOrderActivities.length === 0 ? (
                  <p className="text-slate-400 text-[11px]">No audit activities recorded for this order.</p>
                ) : (
                  selectedOrderActivities.map((act) => (
                    <div key={act.id} className="p-2 bg-slate-950/70 border border-slate-800 rounded text-[11px] flex items-center justify-between">
                      <div>
                        <span className="font-bold text-blue-400 mr-2">{act.activity_type}</span>
                        <span className="text-slate-300 font-sans">{act.description}</span>
                      </div>
                      <span className="text-slate-400 text-[10px] flex-shrink-0">{new Date(act.timestamp).toLocaleTimeString()}</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                onClick={() => setSelectedOrder(null)}
                className="px-4 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 font-sans text-xs font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 4. Modal: Order Replace Form */}
      {replacingOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-5 shadow-2xl flex flex-col gap-4 font-sans text-xs">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <RotateCcw className="w-4 h-4 text-amber-400" />
                <h3 className="text-sm font-bold text-slate-100">Replace Simulated Order</h3>
              </div>
              <button
                onClick={() => setReplacingOrder(null)}
                className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200"
              >
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <p className="text-slate-300 text-[11px]">
              Replacing order <span className="font-mono font-bold text-slate-100">{replacingOrder.id}</span> for <span className="font-mono font-bold text-slate-100">{replacingOrder.symbol}</span>.
            </p>

            <form onSubmit={handleConfirmReplace} className="flex flex-col gap-3 font-mono">
              <div>
                <label className="text-slate-400 mb-1 block font-medium font-sans">New Quantity</label>
                <input
                  type="number"
                  step="any"
                  value={replaceQty}
                  onChange={(e) => setReplaceQty(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-100"
                />
              </div>

              {(replacingOrder.type === 'limit' || replacingOrder.type === 'stop_limit') && (
                <div>
                  <label className="text-slate-400 mb-1 block font-medium font-sans">New Limit Price ($)</label>
                  <input
                    type="number"
                    step="any"
                    value={replaceLimitPrice}
                    onChange={(e) => setReplaceLimitPrice(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-100"
                  />
                </div>
              )}

              {(replacingOrder.type === 'stop' || replacingOrder.type === 'stop_limit') && (
                <div>
                  <label className="text-slate-400 mb-1 block font-medium font-sans">New Stop Price ($)</label>
                  <input
                    type="number"
                    step="any"
                    value={replaceStopPrice}
                    onChange={(e) => setReplaceStopPrice(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-slate-100"
                  />
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-800 font-sans">
                <button
                  type="button"
                  onClick={() => setReplacingOrder(null)}
                  className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={replaceSubmitting}
                  className="px-4 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-white font-bold"
                >
                  {replaceSubmitting ? 'Replacing...' : 'Confirm Replace'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
export default TradingWorkbenchPanel
