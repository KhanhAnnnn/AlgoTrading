import React, { useState } from 'react'
import type { PaperAccount, PaperPosition, PaperOrder } from '../types'
import { Briefcase, ShieldCheck, RefreshCw } from 'lucide-react'

interface PaperTradingPanelProps {
  account: PaperAccount | null
  positions: PaperPosition[]
  orders: PaperOrder[]
  loading: boolean
  onRefresh: () => void
}

export const PaperTradingPanel: React.FC<PaperTradingPanelProps> = ({
  account,
  positions,
  orders,
  loading,
  onRefresh,
}) => {
  const [activeTab, setActiveTab] = useState<'positions' | 'orders'>('orders')

  return (
    <div className="flex flex-col h-full bg-slate-950 rounded-xl border border-slate-800 overflow-hidden shadow-xl">
      {/* Panel Header */}
      <div className="p-3 bg-slate-900/80 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Briefcase className="w-4 h-4 text-emerald-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            Alpaca Paper Portfolio
          </h2>
          <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-950/70 text-emerald-400 border border-emerald-800/60 font-mono text-[10px] font-semibold">
            <ShieldCheck className="w-3 h-3" />
            READ-ONLY
          </span>
        </div>

        <button
          onClick={onRefresh}
          disabled={loading}
          className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-50 transition-colors"
          title="Refresh Alpaca Paper Data"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Account Metric Cards */}
      <div className="grid grid-cols-3 gap-2 p-3 bg-slate-900/30 border-b border-slate-800 text-xs font-mono">
        <div className="bg-slate-950/80 p-2.5 rounded-lg border border-slate-800">
          <span className="text-[10px] text-slate-500 block mb-0.5">Portfolio Equity</span>
          <span className="text-sm font-bold text-slate-100">
            ${account ? account.equity.toLocaleString('en-US', { minimumFractionDigits: 2 }) : '100,000.00'}
          </span>
        </div>

        <div className="bg-slate-950/80 p-2.5 rounded-lg border border-slate-800">
          <span className="text-[10px] text-slate-500 block mb-0.5">Cash Balance</span>
          <span className="text-sm font-bold text-emerald-400">
            ${account ? account.cash.toLocaleString('en-US', { minimumFractionDigits: 2 }) : '100,000.00'}
          </span>
        </div>

        <div className="bg-slate-950/80 p-2.5 rounded-lg border border-slate-800">
          <span className="text-[10px] text-slate-500 block mb-0.5">Buying Power</span>
          <span className="text-sm font-bold text-blue-400">
            ${account ? account.buying_power.toLocaleString('en-US', { minimumFractionDigits: 2 }) : '200,000.00'}
          </span>
        </div>
      </div>

      {/* Sub Tabs */}
      <div className="flex border-b border-slate-800 text-xs font-semibold bg-slate-950">
        <button
          onClick={() => setActiveTab('orders')}
          className={`flex-1 py-2 text-center border-b-2 transition-colors ${
            activeTab === 'orders'
              ? 'border-blue-500 text-blue-400 bg-slate-900/40'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Orders ({orders.length})
        </button>
        <button
          onClick={() => setActiveTab('positions')}
          className={`flex-1 py-2 text-center border-b-2 transition-colors ${
            activeTab === 'positions'
              ? 'border-blue-500 text-blue-400 bg-slate-900/40'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Positions ({positions.length})
        </button>
      </div>

      {/* Table Content */}
      <div className="flex-1 overflow-y-auto p-2">
        {activeTab === 'orders' ? (
          orders.length === 0 ? (
            <div className="p-6 text-center text-slate-500 text-xs italic">
              No orders submitted in Paper Trading account.
            </div>
          ) : (
            <div className="space-y-1.5 font-mono text-xs">
              {orders.map((ord) => {
                const isBuy = ord.side.toLowerCase() === 'buy'
                return (
                  <div
                    key={ord.id}
                    className="p-2.5 bg-slate-900/40 rounded-lg border border-slate-800/60 flex items-center justify-between"
                  >
                    <div>
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="font-bold text-slate-200">{ord.symbol}</span>
                        <span
                          className={`text-[10px] px-1.5 py-0.2 rounded font-bold ${
                            isBuy
                              ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                              : 'bg-rose-950 text-rose-400 border border-rose-800'
                          }`}
                        >
                          {ord.side.toUpperCase()}
                        </span>
                        <span className="text-slate-400 text-[11px]">
                          {ord.filled_qty}/{ord.qty} units
                        </span>
                      </div>
                      <span className="text-[10px] text-slate-500">
                        {new Date(ord.submitted_at).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        })}
                      </span>
                    </div>

                    <div className="text-right">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          ord.status === 'filled'
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : ord.status === 'accepted' || ord.status === 'new'
                            ? 'bg-blue-950 text-blue-400 border border-blue-800'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {ord.status}
                      </span>
                      {ord.filled_avg_price && (
                        <span className="block text-[11px] text-slate-300 mt-0.5">
                          @ ${ord.filled_avg_price.toFixed(2)}
                        </span>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )
        ) : positions.length === 0 ? (
          <div className="p-6 text-center text-slate-500 text-xs italic">
            No open stock positions currently held.
          </div>
        ) : (
          <div className="space-y-1.5 font-mono text-xs">
            {positions.map((pos) => {
              const isGain = pos.unrealized_pl >= 0
              return (
                <div
                  key={pos.symbol}
                  className="p-2.5 bg-slate-900/40 rounded-lg border border-slate-800/60 flex items-center justify-between"
                >
                  <div>
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-bold text-slate-200">{pos.symbol}</span>
                      <span className="text-slate-400 text-[11px]">{pos.qty} units</span>
                    </div>
                    <span className="text-[10px] text-slate-500">
                      Avg: ${pos.avg_entry_price.toFixed(2)} | Current: ${pos.current_price.toFixed(2)}
                    </span>
                  </div>

                  <div className="text-right">
                    <span className="font-bold text-slate-200 block">
                      ${pos.market_value.toFixed(2)}
                    </span>
                    <span
                      className={`text-[11px] font-bold ${
                        isGain ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {isGain ? '+' : ''}
                      {pos.unrealized_pl.toFixed(2)} ({isGain ? '+' : ''}
                      {(pos.unrealized_plpc * 100).toFixed(2)}%)
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Security Safety Footer */}
      <div className="p-2 bg-slate-950 border-t border-slate-800/80 text-[10px] text-slate-500 flex items-center justify-center gap-1.5">
        <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
        <span>Read-only inspection mode. Trade order execution is strictly disabled.</span>
      </div>
    </div>
  )
}
