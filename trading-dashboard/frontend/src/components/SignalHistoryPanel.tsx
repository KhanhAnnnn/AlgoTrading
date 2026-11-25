import React from 'react'
import type { TradingSignal } from '../types'
import { Zap, TrendingUp, TrendingDown, ChevronRight } from 'lucide-react'

interface SignalHistoryPanelProps {
  signals: TradingSignal[]
  onSelectSignal: (signal: TradingSignal) => void
}

export const SignalHistoryPanel: React.FC<SignalHistoryPanelProps> = ({
  signals,
  onSelectSignal,
}) => {
  return (
    <div className="flex flex-col h-full bg-slate-950 rounded-xl border border-slate-800 overflow-hidden shadow-xl">
      {/* Panel Header */}
      <div className="p-3 bg-slate-900/80 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            Pipeline Signals Log
          </h2>
          <span className="px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 text-[10px] font-mono">
            {signals.length} Emitted
          </span>
        </div>
      </div>

      {/* Signals Table / List */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60 p-2 space-y-1.5">
        {signals.length === 0 ? (
          <div className="p-6 text-center text-slate-500 text-xs italic">
            No algorithmic trading signals recorded yet.
          </div>
        ) : (
          signals.map((sig) => {
            const isBuy = sig.signal === 'BUY'
            return (
              <div
                key={sig.id}
                data-testid="signal-item"
                onClick={() => onSelectSignal(sig)}
                className="p-2.5 bg-slate-900/40 hover:bg-slate-900/80 rounded-lg transition-all cursor-pointer border border-slate-800/50 flex items-center justify-between group"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`p-1.5 rounded-lg ${
                      isBuy
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                    }`}
                  >
                    {isBuy ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                  </div>

                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-100">{sig.symbol}</span>
                      {sig.symbol.toUpperCase().includes('TEST') ? (
                        <span className="text-[9px] px-1 py-0.2 rounded bg-amber-950 text-amber-300 border border-amber-800 font-mono font-bold">
                          TEST FIXTURE
                        </span>
                      ) : (
                        <span className="text-[9px] px-1 py-0.2 rounded bg-blue-950 text-blue-300 border border-blue-800 font-mono font-bold">
                          STREAM PRODUCTION
                        </span>
                      )}
                      <span
                        className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                          isBuy
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : 'bg-rose-950 text-rose-400 border border-rose-800'
                        }`}
                      >
                        {sig.signal}
                      </span>
                      <span className="text-xs font-bold font-mono text-slate-300">
                        {sig.price != null ? `$${sig.price.toFixed(2)}` : 'Market'}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-500 font-mono">
                      {new Date(sig.timestamp).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {sig.sentiment_score !== undefined && (
                    <div className="text-right hidden sm:block">
                      <span className="text-[10px] text-slate-500 block">Sentiment</span>
                      <span
                        className={`text-xs font-mono font-bold ${
                          sig.sentiment_score > 0
                            ? 'text-emerald-400'
                            : sig.sentiment_score < 0
                            ? 'text-rose-400'
                            : 'text-slate-400'
                        }`}
                      >
                        {sig.sentiment_score > 0 ? '+' : ''}
                        {sig.sentiment_score.toFixed(2)}
                      </span>
                    </div>
                  )}

                  <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-slate-300 transition-colors" />
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
