import React from 'react'
import type { TradingSignal, PaperOrder } from '../types'
import { X, TrendingUp, TrendingDown, Clock, ShieldCheck, CheckCircle2 } from 'lucide-react'

interface SignalModalProps {
  signal: TradingSignal | null
  matchedOrder?: PaperOrder | null
  onClose: () => void
}

export const SignalModal: React.FC<SignalModalProps> = ({
  signal,
  matchedOrder,
  onClose,
}) => {
  if (!signal) return null

  const isBuy = signal.signal === 'BUY'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-lg bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl p-6 text-slate-100 font-sans">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-4">
          <div className="flex items-center gap-3">
            <div
              className={`p-2.5 rounded-xl ${
                isBuy
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
              }`}
            >
              {isBuy ? <TrendingUp className="w-6 h-6" /> : <TrendingDown className="w-6 h-6" />}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xl font-bold tracking-tight">{signal.symbol}</span>
                <span
                  className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                    isBuy
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                      : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                  }`}
                >
                  {signal.signal} SIGNAL
                </span>
              </div>
              <span className="text-xs text-slate-400 font-mono">ID: {signal.id}</span>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Signal Attributes Grid */}
        <div className="grid grid-cols-2 gap-3 mb-5 font-mono text-xs">
          <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800">
            <span className="text-slate-400 block mb-1">Execution / Signal Price</span>
            <span className="text-lg font-bold text-slate-100">{signal.price != null ? `$${signal.price.toFixed(2)}` : 'Market Price'}</span>
          </div>

          <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800">
            <span className="text-slate-400 block mb-1">Sentiment Score</span>
            {signal.sentiment_score !== undefined ? (
              <span
                className={`text-lg font-bold ${
                  signal.sentiment_score > 0.05
                    ? 'text-emerald-400'
                    : signal.sentiment_score < -0.05
                    ? 'text-rose-400'
                    : 'text-slate-300'
                }`}
              >
                {signal.sentiment_score > 0 ? '+' : ''}
                {signal.sentiment_score.toFixed(3)}
              </span>
            ) : (
              <span className="text-slate-500 italic">N/A</span>
            )}
          </div>

          <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800">
            <span className="text-slate-400 block mb-1">SMA 20 at Event</span>
            <span className="text-sm font-semibold text-cyan-400">
              {signal.sma_20 ? `$${signal.sma_20.toFixed(2)}` : 'N/A'}
            </span>
          </div>

          <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800">
            <span className="text-slate-400 block mb-1">SMA 50 at Event</span>
            <span className="text-sm font-semibold text-amber-400">
              {signal.sma_50 ? `$${signal.sma_50.toFixed(2)}` : 'N/A'}
            </span>
          </div>
        </div>

        {/* Timestamp Info */}
        <div className="bg-slate-950/40 p-3 rounded-xl border border-slate-800/80 mb-5 text-xs flex items-center gap-2 text-slate-300">
          <Clock className="w-4 h-4 text-slate-400 shrink-0" />
          <div>
            <span className="text-slate-400">Event Time: </span>
            <span className="font-mono">{new Date(signal.timestamp).toLocaleString()}</span>
            <span className="text-slate-500 font-mono ml-2 text-[11px]">({signal.timestamp})</span>
          </div>
        </div>

        {/* Alpaca Paper Trading Execution Status */}
        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-bold text-slate-200">
              Alpaca Paper Trading Integration
            </span>
          </div>

          {matchedOrder ? (
            <div className="space-y-1.5 text-xs font-mono">
              <div className="flex justify-between">
                <span className="text-slate-400">Matched Order ID:</span>
                <span className="text-slate-200">{matchedOrder.id.slice(0, 18)}...</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Status:</span>
                <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-950/60 text-emerald-400 border border-emerald-800">
                  {matchedOrder.status.toUpperCase()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Filled Qty:</span>
                <span className="text-slate-200">
                  {matchedOrder.filled_qty} / {matchedOrder.qty} shares
                </span>
              </div>
              {matchedOrder.filled_avg_price && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Filled Avg Price:</span>
                  <span className="text-slate-200">${matchedOrder.filled_avg_price.toFixed(2)}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="text-xs text-slate-400 space-y-1">
              <p className="flex items-center gap-1.5 text-slate-300">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                Pipeline signal emitted by Apache Flink SQL job.
              </p>
              <p className="text-[11px] text-slate-500 font-mono">
                Source: Kafka topic `trading-signals` → Signal Handler (Paper Trading Safe Mode)
              </p>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="mt-5 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
