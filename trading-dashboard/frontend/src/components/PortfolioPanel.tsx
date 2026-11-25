import React, { useState, useEffect } from 'react'
import type { PortfolioSummary } from '../types'
import {
  ShieldCheck,
  CheckCircle2,
  Clock,
  AlertCircle,
  XCircle,
  RefreshCw,
  Layers,
  FileText,
  Info,
  AlertTriangle,
  ServerOff
} from 'lucide-react'

interface PortfolioPanelProps {
  apiBase?: string
}

export const PortfolioPanel: React.FC<PortfolioPanelProps> = ({
  apiBase = 'http://127.0.0.1:8005'
}) => {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [orderFilter, setOrderFilter] = useState<'all' | 'open' | 'filled' | 'canceled'>('all')
  const [refreshing, setRefreshing] = useState<boolean>(false)
  const [fetchError, setFetchError] = useState<string | null>(null)

  const fetchPortfolioData = async () => {
    try {
      setFetchError(null)
      const res = await fetch(`${apiBase}/api/paper/summary`)
      if (res.ok) {
        const data: PortfolioSummary = await res.json()
        setSummary(data)
      } else {
        setFetchError(`HTTP ${res.status}: Failed to reach portfolio telemetry`)
      }
    } catch (err: any) {
      console.error('Error fetching paper summary:', err)
      setFetchError(err.message || 'Network connection failed')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchPortfolioData()
    const timer = setInterval(fetchPortfolioData, 8000)
    return () => clearInterval(timer)
  }, [apiBase])

  const handleRefresh = () => {
    setRefreshing(true)
    fetchPortfolioData()
  }

  // 1. Initial Loading State
  if (loading && !summary) {
    return (
      <div className="flex flex-col items-center justify-center py-20 bg-slate-900/50 border border-slate-800 rounded-xl text-center font-mono">
        <RefreshCw className="w-8 h-8 text-blue-400 animate-spin mb-4" />
        <h3 className="text-sm font-bold text-slate-200">Connecting to Alpaca Paper Trading API...</h3>
        <p className="text-xs text-slate-400 mt-1">Retrieving verified account balances, positions, and orders telemetry.</p>
      </div>
    )
  }

  // 2. Fatal API Unavailable State
  if (summary?.status === 'UNAVAILABLE' || (fetchError && !summary)) {
    return (
      <div className="flex flex-col gap-4 text-slate-200">
        <div className="p-6 bg-rose-950/40 border border-rose-800 rounded-xl flex flex-col items-center text-center">
          <ServerOff className="w-10 h-10 text-rose-400 mb-3" />
          <h3 className="text-sm font-bold text-rose-200 uppercase tracking-wider">
            Alpaca Paper Trading API Unavailable
          </h3>
          <p className="text-xs text-rose-300/80 max-w-lg mt-1 font-mono">
            {summary?.error || fetchError || 'Unable to connect to Alpaca Paper Trading endpoint. Balances and open positions cannot be verified.'}
          </p>
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-rose-900 hover:bg-rose-800 text-rose-100 rounded text-xs font-mono font-bold transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              Retry Connection
            </button>
          </div>
        </div>
      </div>
    )
  }

  const account = summary?.account
  const positions = summary?.positions || []
  const allOrders = summary?.recent_orders || []
  const isFallback = summary?.is_fallback || false

  // Filter orders
  const filteredOrders = allOrders.filter((ord) => {
    const st = ord.status.toLowerCase()
    if (orderFilter === 'open') return ['accepted', 'pending_new', 'new', 'accepted_for_bidding'].includes(st)
    if (orderFilter === 'filled') return st === 'filled'
    if (orderFilter === 'canceled') return ['canceled', 'cancelled', 'rejected', 'expired'].includes(st)
    return true
  })

  // Status badge styling
  const renderStatusBadge = (status: string) => {
    const st = status.toLowerCase()
    if (st === 'filled') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-800">
          <CheckCircle2 className="w-3 h-3" /> FILLED
        </span>
      )
    }
    if (['accepted', 'pending_new', 'new'].includes(st)) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-blue-950/80 text-blue-400 border border-blue-800">
          <Clock className="w-3 h-3" /> ACCEPTED
        </span>
      )
    }
    if (st === 'partially_filled') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-950/80 text-amber-400 border border-amber-800">
          <AlertCircle className="w-3 h-3" /> PARTIAL
        </span>
      )
    }
    if (['canceled', 'cancelled', 'expired'].includes(st)) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-800 text-slate-400 border border-slate-700">
          <XCircle className="w-3 h-3" /> CANCELLED
        </span>
      )
    }
    if (st === 'rejected') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-950/80 text-rose-400 border border-rose-800">
          <XCircle className="w-3 h-3" /> REJECTED
        </span>
      )
    }
    return (
      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-800 text-slate-400">
        {status.toUpperCase()}
      </span>
    )
  }

  return (
    <div className="flex flex-col gap-4 text-slate-200">
      {/* Degraded Last-Known-Good Warning Banner */}
      {isFallback && (
        <div className="p-3 bg-amber-950/70 border border-amber-800 rounded-lg flex items-center justify-between gap-3 text-xs font-mono">
          <div className="flex items-center gap-2 text-amber-300">
            <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
            <span>
              {summary?.fallback_reason || 'Alpaca API connection interrupted. Displaying cached last-known-good portfolio snapshot.'}
            </span>
          </div>
          <span className="text-amber-400 text-[10px] shrink-0">
            Cache age: {summary?.cache_age_sec}s
          </span>
        </div>
      )}

      {/* Read-Only Safety Banner */}
      <div className="p-3 bg-slate-900 border border-slate-800 rounded-lg flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
          <div className="text-xs">
            <span className="font-semibold text-emerald-400 uppercase tracking-wider">
              Alpaca Paper Portfolio (Read-Only Mode):{' '}
            </span>
            <span className="text-slate-300">
              Live telemetry streamed from Alpaca Paper API. Account ID: <code className="bg-slate-800 px-1 py-0.5 rounded text-cyan-300 font-mono">{summary?.account_id || account?.id || 'N/A'}</code>.
              Guard: <code className="bg-slate-800 px-1 py-0.5 rounded text-amber-300 font-mono">TRADING_MODE=DRY_RUN</code>.
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <span className="text-[10px] font-mono text-slate-400 hidden sm:inline">
            Updated: {summary?.source_timestamp ? new Date(summary.source_timestamp).toLocaleTimeString() : 'Just now'} (Age: {summary?.cache_age_sec || 0}s)
          </span>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-xs font-mono text-slate-300 transition-colors shrink-0"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Account Balances Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 font-mono">
        {/* Equity */}
        <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Total Equity</span>
          <div className="text-lg font-bold text-white mt-1">
            ${account?.equity !== undefined ? account.equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : 'N/A'}
          </div>
          <span className="text-[10px] text-slate-500">Currency: {account?.currency || 'USD'}</span>
        </div>

        {/* Cash */}
        <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Cash Balance</span>
          <div className="text-lg font-bold text-slate-200 mt-1">
            ${account?.cash !== undefined ? account.cash.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : 'N/A'}
          </div>
          <span className="text-[10px] text-slate-500">Status: {account?.status || 'ACTIVE'}</span>
        </div>

        {/* Buying Power */}
        <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Buying Power</span>
          <div className="text-lg font-bold text-cyan-400 mt-1">
            ${account?.buying_power !== undefined ? account.buying_power.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : 'N/A'}
          </div>
          <span className="text-[10px] text-slate-500">Margin: Regular</span>
        </div>

        {/* Unrealized P/L */}
        <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Unrealized P/L</span>
          <div className={`text-lg font-bold mt-1 ${(summary?.total_unrealized_pl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {(summary?.total_unrealized_pl || 0) >= 0 ? '+' : ''}
            ${(summary?.total_unrealized_pl || 0).toFixed(2)}
          </div>
          <span className="text-[10px] text-slate-500">
            {(summary?.total_unrealized_plpc || 0) >= 0 ? '+' : ''}
            {(summary?.total_unrealized_plpc || 0).toFixed(2)}%
          </span>
        </div>

        {/* Open Positions */}
        <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Positions Active</span>
          <div className="text-lg font-bold text-purple-300 mt-1">
            {positions.length}
          </div>
          <span className="text-[10px] text-slate-500">Cost: ${(summary?.total_cost_basis || 0).toFixed(2)}</span>
        </div>

        {/* Orders Count */}
        <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Paper Orders</span>
          <div className="text-lg font-bold text-amber-300 mt-1">
            {summary?.filled_orders_count || 0} Filled
          </div>
          <span className="text-[10px] text-slate-500">{summary?.open_orders_count || 0} Open</span>
        </div>
      </div>

      {/* Positions Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-purple-400" />
            <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
              Open Positions (Stocks & Crypto)
            </h4>
          </div>
          <span className="text-xs font-mono text-slate-400">Total: {positions.length}</span>
        </div>

        {positions.length === 0 ? (
          <div className="py-8 text-center text-slate-500 text-xs italic">
            No open positions currently held in Alpaca Paper Trading account.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono text-left">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="pb-2">Symbol</th>
                  <th className="pb-2">Side</th>
                  <th className="pb-2 text-right">Quantity</th>
                  <th className="pb-2 text-right">Entry Price</th>
                  <th className="pb-2 text-right">Market Price</th>
                  <th className="pb-2 text-right">Market Value</th>
                  <th className="pb-2 text-right">Unrealized P/L</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {positions.map((pos, idx) => {
                  const isCrypto = pos.symbol.includes('USD') || pos.symbol.includes('/')
                  const isPositive = pos.unrealized_pl >= 0
                  return (
                    <tr key={`${pos.symbol}-${idx}`} className="hover:bg-slate-800/40 transition-colors">
                      <td className="py-2.5 font-bold text-slate-100 flex items-center gap-2">
                        <span>{pos.symbol}</span>
                        <span className={`text-[9px] px-1.5 py-0.2 rounded font-sans uppercase ${isCrypto ? 'bg-amber-950 text-amber-400 border border-amber-800' : 'bg-blue-950 text-blue-400 border border-blue-800'}`}>
                          {isCrypto ? 'Crypto' : 'Stock'}
                        </span>
                      </td>
                      <td className="py-2.5 uppercase text-slate-400 font-semibold">{pos.side}</td>
                      <td className="py-2.5 text-right text-slate-200">{pos.qty}</td>
                      <td className="py-2.5 text-right text-slate-300">${pos.avg_entry_price.toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                      <td className="py-2.5 text-right text-slate-200">${pos.current_price.toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                      <td className="py-2.5 text-right font-bold text-white">${pos.market_value.toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                      <td className={`py-2.5 text-right font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {isPositive ? '+' : ''}${pos.unrealized_pl.toFixed(2)} ({isPositive ? '+' : ''}{(pos.unrealized_plpc * 100).toFixed(2)}%)
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Orders Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-cyan-400" />
            <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
              Recent Alpaca Paper Orders
            </h4>
          </div>

          {/* Filter Pills */}
          <div className="flex items-center gap-1 bg-slate-950 p-0.5 rounded border border-slate-800 text-[11px] font-mono">
            {(['all', 'open', 'filled', 'canceled'] as const).map((filter) => (
              <button
                key={filter}
                onClick={() => setOrderFilter(filter)}
                className={`px-2.5 py-0.5 rounded transition-colors uppercase ${orderFilter === filter ? 'bg-blue-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
              >
                {filter}
              </button>
            ))}
          </div>
        </div>

        {filteredOrders.length === 0 ? (
          <div className="py-8 text-center text-slate-500 text-xs italic">
            No paper trading orders matching the selected filter ({orderFilter}).
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono text-left">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="pb-2">Time</th>
                  <th className="pb-2">Symbol</th>
                  <th className="pb-2">Side</th>
                  <th className="pb-2">Type</th>
                  <th className="pb-2 text-right">Quantity</th>
                  <th className="pb-2 text-right">Fill Price</th>
                  <th className="pb-2 text-center">Status</th>
                  <th className="pb-2 text-right">Client Order ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredOrders.map((ord) => {
                  const isBuy = ord.side.toLowerCase() === 'buy'
                  return (
                    <tr key={ord.id} className="hover:bg-slate-800/40 transition-colors">
                      <td className="py-2 text-slate-400 whitespace-nowrap">
                        {ord.submitted_at ? new Date(ord.submitted_at).toLocaleString() : 'N/A'}
                      </td>
                      <td className="py-2 font-bold text-slate-100">{ord.symbol}</td>
                      <td className={`py-2 uppercase font-bold ${isBuy ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {ord.side}
                      </td>
                      <td className="py-2 text-slate-300 uppercase">{ord.type}</td>
                      <td className="py-2 text-right text-slate-200">{ord.filled_qty || ord.qty || 'N/A'}</td>
                      <td className="py-2 text-right text-slate-300">
                        {ord.filled_avg_price ? `$${Number(ord.filled_avg_price).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'}
                      </td>
                      <td className="py-2 text-center">
                        {renderStatusBadge(ord.status)}
                      </td>
                      <td className="py-2 text-right text-slate-500 text-[10px] truncate max-w-[140px]" title={ord.client_order_id || ord.id}>
                        {ord.client_order_id || ord.id.slice(0, 8)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Explanatory Distinction Box */}
      <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg flex items-start gap-2.5 text-xs text-slate-400">
        <Info className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="text-slate-300 font-semibold">Kafka Signal vs Alpaca Paper Order Distinction:</p>
          <p>
            <strong>Kafka Signals</strong> (shown in the Terminal panel) represent analytical trading triggers generated by Flink stream processing based on moving average crossovers and sentiment rules.
            <strong>Paper Orders</strong> (shown above) represent actual broker execution transactions recorded in the Alpaca Paper Trading account. Under <code className="text-amber-300 bg-slate-800 px-1 py-0.2 rounded font-mono">DRY_RUN</code>, raw Kafka signals are logged without submitting orders to Alpaca.
          </p>
        </div>
      </div>
    </div>
  )
}
