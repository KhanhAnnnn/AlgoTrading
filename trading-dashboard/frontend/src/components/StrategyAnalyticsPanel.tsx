import React, { useState, useEffect } from 'react'
import type { StrategyMetric, EquityCurveData, HistoricalTrade, SplitPerformance } from '../types'
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  ShieldCheck,
  Activity,
  Layers,
  Info
} from 'lucide-react'

interface StrategyAnalyticsPanelProps {
  asset: string
  apiBase?: string
}

export const StrategyAnalyticsPanel: React.FC<StrategyAnalyticsPanelProps> = ({
  asset,
  apiBase = 'http://localhost:8005'
}) => {
  const [selectedStrategyId, setSelectedStrategyId] = useState<number>(1)
  const [selectedSplit, setSelectedSplit] = useState<string>('FULL_PERIOD')
  const [strategies, setStrategies] = useState<StrategyMetric[]>([])
  const [equityCurve, setEquityCurve] = useState<EquityCurveData | null>(null)
  const [trades, setTrades] = useState<HistoricalTrade[]>([])
  const [splits, setSplits] = useState<SplitPerformance[]>([])

  // Fetch strategies list
  useEffect(() => {
    let isMounted = true
    const fetchStrategies = async () => {
      try {
        const res = await fetch(`${apiBase}/api/analytics/strategies?asset=${encodeURIComponent(asset)}&split=${selectedSplit}`)
        if (res.ok) {
          const data = await res.json()
          if (isMounted && data.strategies) {
            setStrategies(data.strategies)
          }
        }
      } catch (err) {
        console.error('Error fetching strategies:', err)
      }
    }
    fetchStrategies()
    return () => { isMounted = false }
  }, [asset, selectedSplit, apiBase])

  // Fetch equity curve and trades for selected strategy
  useEffect(() => {
    let isMounted = true

    const fetchData = async () => {
      try {
        const [eqRes, trRes, spRes] = await Promise.all([
          fetch(`${apiBase}/api/analytics/equity-curve?asset=${encodeURIComponent(asset)}&strategy_id=${selectedStrategyId}`),
          fetch(`${apiBase}/api/analytics/trades?asset=${encodeURIComponent(asset)}&strategy_id=${selectedStrategyId}`),
          fetch(`${apiBase}/api/analytics/splits?asset=${encodeURIComponent(asset)}&strategy_id=${selectedStrategyId}`)
        ])

        if (eqRes.ok) {
          const eqData = await eqRes.json()
          if (isMounted) setEquityCurve(eqData)
        }
        if (trRes.ok) {
          const trData = await trRes.json()
          if (isMounted && trData.trades) setTrades(trData.trades)
        }
        if (spRes.ok) {
          const spData = await spRes.json()
          if (isMounted && spData.splits) setSplits(spData.splits)
        }
      } catch (err) {
        console.error('Error fetching analytics details:', err)
      }
    }

    fetchData()
    return () => { isMounted = false }
  }, [asset, selectedStrategyId, apiBase])

  const activeStrategy = strategies.find(s => s.strategy_id === selectedStrategyId) || strategies[0]

  // Render SVG Equity Curve
  const renderEquityCurveSVG = () => {
    if (!equityCurve || !equityCurve.points || equityCurve.points.length < 2) {
      return (
        <div className="h-48 flex items-center justify-center text-slate-500 text-sm italic">
          No equity curve data available for this strategy.
        </div>
      )
    }

    const pts = equityCurve.points
    const equities = pts.map(p => p.equity)
    const minEq = Math.min(...equities) * 0.998
    const maxEq = Math.max(...equities) * 1.002
    const rangeEq = maxEq - minEq || 1

    const width = 640
    const height = 180
    const padding = 20

    const pointsStr = pts.map((p, i) => {
      const x = padding + (i / (pts.length - 1)) * (width - padding * 2)
      const y = height - padding - ((p.equity - minEq) / rangeEq) * (height - padding * 2)
      return `${x},${y}`
    }).join(' ')

    const isPositive = (equityCurve.final_equity >= equityCurve.initial_capital)
    const strokeColor = isPositive ? '#10b981' : '#f43f5e'

    const firstPt = `${padding},${height - padding}`
    const lastPt = `${width - padding},${height - padding}`
    const areaStr = `${firstPt} ${pointsStr} ${lastPt}`

    return (
      <div className="relative w-full">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-48 overflow-visible">
          <defs>
            <linearGradient id="eqGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.25" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0.0" />
            </linearGradient>
          </defs>
          {/* Baseline horizontal grid line */}
          <line
            x1={padding}
            y1={height - padding - ((100000 - minEq) / rangeEq) * (height - padding * 2)}
            x2={width - padding}
            y2={height - padding - ((100000 - minEq) / rangeEq) * (height - padding * 2)}
            stroke="#334155"
            strokeDasharray="4 4"
            strokeWidth="1"
          />
          {/* Equity Area & Line */}
          <polygon points={areaStr} fill="url(#eqGradient)" />
          <polyline fill="none" stroke={strokeColor} strokeWidth="2" points={pointsStr} />
        </svg>
        <div className="flex justify-between text-[11px] text-slate-500 font-mono mt-1 px-2">
          <span>Start: ${equityCurve.initial_capital.toLocaleString()}</span>
          <span>End: ${equityCurve.final_equity.toLocaleString()}</span>
        </div>
      </div>
    )
  }

  // Render SVG Drawdown Chart
  const renderDrawdownSVG = () => {
    if (!equityCurve || !equityCurve.points || equityCurve.points.length < 2) {
      return null
    }

    const pts = equityCurve.points
    const drawdowns = pts.map(p => p.drawdown_pct)
    const maxDD = Math.max(...drawdowns, 0.01)

    const width = 640
    const height = 90
    const padding = 15

    const pointsStr = pts.map((p, i) => {
      const x = padding + (i / (pts.length - 1)) * (width - padding * 2)
      const y = padding + (p.drawdown_pct / maxDD) * (height - padding * 2)
      return `${x},${y}`
    }).join(' ')

    const firstPt = `${padding},${padding}`
    const lastPt = `${width - padding},${padding}`
    const areaStr = `${firstPt} ${pointsStr} ${lastPt}`

    return (
      <div className="relative w-full">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-24 overflow-visible">
          <polygon points={areaStr} fill="rgba(244, 63, 94, 0.2)" />
          <polyline fill="none" stroke="#f43f5e" strokeWidth="1.5" points={pointsStr} />
        </svg>
        <div className="flex justify-between text-[11px] text-slate-500 font-mono mt-1 px-2">
          <span>Peak: 0.00% Drawdown</span>
          <span className="text-rose-400 font-semibold">Max DD: -{maxDD.toFixed(2)}%</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 text-slate-200">
      {/* Top Banner: Production Strategy Notice */}
      <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-lg flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
          <div className="text-xs">
            <span className="font-semibold text-emerald-400 uppercase tracking-wider">Production Integrity Guard: </span>
            <span className="text-slate-300">
              Only <strong>Strategy 1 (PDF Baseline)</strong> is active in Flink stream processing under <code className="bg-slate-800 px-1.5 py-0.5 rounded text-amber-300">TRADING_MODE=DRY_RUN</code>. Strategies 2–5 are quantitative models for analytical study and backtesting.
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-slate-400">Sample Split:</span>
          <select
            value={selectedSplit}
            onChange={(e) => setSelectedSplit(e.target.value)}
            className="bg-slate-950 border border-slate-700 text-xs text-slate-200 rounded px-2 py-1 font-mono focus:outline-none focus:border-blue-500"
          >
            <option value="FULL_PERIOD">Full Dataset (100%)</option>
            <option value="TRAIN_SAMPLE">Train In-Sample (60%)</option>
            <option value="VAL_SAMPLE">Validation (20%)</option>
            <option value="TEST_OUT_OF_SAMPLE">Test Out-of-Sample (20%)</option>
          </select>
        </div>
      </div>

      {/* Strategy Switcher Tabs */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
        {strategies.map((strat) => {
          const isSelected = strat.strategy_id === selectedStrategyId
          return (
            <button
              key={strat.strategy_id}
              onClick={() => setSelectedStrategyId(strat.strategy_id)}
              className={`p-3 rounded-lg border text-left transition-all duration-150 flex flex-col justify-between ${
                isSelected
                  ? 'bg-blue-950/40 border-blue-500 text-white shadow-lg shadow-blue-950/20'
                  : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded uppercase font-semibold bg-slate-800 text-slate-300">
                    S{strat.strategy_id}
                  </span>
                  {strat.is_production ? (
                    <span className="text-[9px] font-mono bg-emerald-950/80 text-emerald-400 border border-emerald-800 px-1.5 py-0.5 rounded font-semibold">
                      PRODUCTION
                    </span>
                  ) : (
                    <span className="text-[9px] font-mono bg-slate-800/80 text-slate-400 px-1.5 py-0.5 rounded">
                      RESEARCH
                    </span>
                  )}
                </div>
                <div className="font-semibold text-xs text-slate-200 line-clamp-1">{strat.short_title}</div>
                <div className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">{strat.tag}</div>
              </div>

              <div className="mt-3 pt-2 border-t border-slate-800/80 flex justify-between items-baseline font-mono text-xs">
                <span className="text-[10px] text-slate-500">Return:</span>
                <span className={`font-semibold ${strat.total_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {strat.total_return_pct >= 0 ? '+' : ''}{strat.total_return_pct.toFixed(2)}%
                </span>
              </div>
            </button>
          )
        })}
      </div>

      {/* Active Strategy Header & Warnings */}
      {activeStrategy && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col gap-3">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-base text-slate-100">{activeStrategy.strategy_name}</h3>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded uppercase font-semibold ${
                  activeStrategy.is_production
                    ? 'bg-emerald-900/40 text-emerald-300 border border-emerald-700'
                    : 'bg-indigo-900/40 text-indigo-300 border border-indigo-700'
                }`}>
                  {activeStrategy.tag}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1 max-w-3xl">{activeStrategy.description}</p>
            </div>
            <div className="text-right shrink-0">
              <span className="text-[10px] uppercase font-mono tracking-wider text-slate-500 block">Asset Evaluated</span>
              <span className="text-sm font-mono font-bold text-cyan-400">{asset}</span>
            </div>
          </div>

          {/* Sample Size Warning Banner */}
          {activeStrategy.sample_size_warning && (
            <div className="flex items-center gap-2 p-2.5 bg-amber-950/40 border border-amber-800/80 rounded text-amber-300 text-xs">
              <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
              <span>
                <strong>Sample Size Warning:</strong> Evaluated on only <strong>{activeStrategy.total_trades} trade(s)</strong> over this sample. Statistical significance is low; do not extrapolate live performance from sparse crossover signals.
              </span>
            </div>
          )}
        </div>
      )}

      {/* Quantitative Metrics Grid */}
      {activeStrategy && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 font-mono">
          {/* Total Return */}
          <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">Total Return</span>
            <div className={`text-lg font-bold mt-1 ${activeStrategy.total_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {activeStrategy.total_return_pct >= 0 ? '+' : ''}{activeStrategy.total_return_pct.toFixed(2)}%
            </div>
            <span className="text-[10px] text-slate-500">Benchmark: {activeStrategy.benchmark_return_pct.toFixed(2)}%</span>
          </div>

          {/* Alpha */}
          <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">Alpha vs Bench</span>
            <div className={`text-lg font-bold mt-1 ${activeStrategy.alpha_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {activeStrategy.alpha_pct >= 0 ? '+' : ''}{activeStrategy.alpha_pct.toFixed(2)}%
            </div>
            <span className="text-[10px] text-slate-500">
              {activeStrategy.total_trades === 0 ? 'Cash Preservation' : 'Active Excess Return'}
            </span>
          </div>

          {/* Max Drawdown */}
          <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">Max Drawdown</span>
            <div className="text-lg font-bold mt-1 text-rose-400">
              -{activeStrategy.max_drawdown_pct.toFixed(2)}%
            </div>
            <span className="text-[10px] text-slate-500">Peak-to-trough</span>
          </div>

          {/* Win Rate */}
          <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">Win Rate</span>
            <div className="text-lg font-bold mt-1 text-cyan-300">
              {activeStrategy.total_trades > 0 && activeStrategy.win_rate_pct != null
                ? `${activeStrategy.win_rate_pct.toFixed(1)}%`
                : 'N/A'}
            </div>
            <span className="text-[10px] text-slate-500">Trades: {activeStrategy.total_trades}</span>
          </div>

          {/* Profit Factor */}
          <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">Profit Factor</span>
            <div className="text-lg font-bold mt-1 text-purple-300">
              {activeStrategy.total_trades > 0 && activeStrategy.profit_factor != null
                ? activeStrategy.profit_factor.toFixed(2)
                : 'N/A'}
            </div>
            <span className="text-[10px] text-slate-500">Sharpe: {activeStrategy.total_trades > 0 ? activeStrategy.sharpe_ratio : 'N/A'}</span>
          </div>

          {/* Frictions (Fees & Slippage) */}
          <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">Total Frictions</span>
            <div className="text-lg font-bold mt-1 text-amber-300">
              ${(activeStrategy.total_fees_usd + activeStrategy.total_slippage_usd).toFixed(2)}
            </div>
            <span className="text-[10px] text-slate-500">Fees: ${activeStrategy.total_fees_usd.toFixed(2)}</span>
          </div>
        </div>
      )}

      {/* Explanatory Banner for Zero-Trade Alpha */}
      {activeStrategy && activeStrategy.total_trades === 0 && (
        <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg flex items-center gap-2.5 text-xs text-slate-400 font-mono">
          <Info className="w-4 h-4 text-cyan-400 shrink-0" />
          <span>
            <strong>Zero-Trade Interpretation:</strong> Strategy executed 0 trades in this partition. Positive Alpha (+{activeStrategy.alpha_pct.toFixed(2)}%) is due to benchmark drawdown while capital remained 100% in cash, not predictive forecasting edge.
          </span>
        </div>
      )}

      {/* Main Charts: Equity Curve & Drawdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Equity Curve */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">Equity Curve Simulation</h4>
            </div>
            <span className="text-[10px] font-mono bg-slate-800 text-slate-300 px-2 py-0.5 rounded">
              Base: $100,000 USD
            </span>
          </div>
          {renderEquityCurveSVG()}
        </div>

        {/* Drawdown Chart */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <TrendingDown className="w-4 h-4 text-rose-400" />
              <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">Underwater Drawdown (%)</h4>
            </div>
            <span className="text-[10px] font-mono bg-rose-950/60 text-rose-400 px-2 py-0.5 rounded border border-rose-900">
              Risk Metric
            </span>
          </div>
          {renderDrawdownSVG()}
        </div>
      </div>

      {/* Out-of-Sample Performance Breakdown */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <Layers className="w-4 h-4 text-cyan-400" />
          <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
            Out-of-Sample Evaluation Matrix (Overfitting Validation)
          </h4>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono text-left">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="pb-2">Split Partition</th>
                <th className="pb-2 text-right">Bars</th>
                <th className="pb-2 text-right">Return (%)</th>
                <th className="pb-2 text-right">Benchmark (%)</th>
                <th className="pb-2 text-right">Alpha (%)</th>
                <th className="pb-2 text-right">Max DD (%)</th>
                <th className="pb-2 text-right">Trades</th>
                <th className="pb-2 text-right">Win Rate (%)</th>
                <th className="pb-2 text-right">Sharpe</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {splits.map((s) => (
                <tr key={s.split} className={s.split === 'TEST_OUT_OF_SAMPLE' ? 'bg-blue-950/20 font-semibold' : ''}>
                  <td className="py-2.5 text-slate-200 flex items-center gap-1.5">
                    {s.split === 'TEST_OUT_OF_SAMPLE' && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>}
                    {s.split_label}
                  </td>
                  <td className="py-2.5 text-right text-slate-400">{s.bars.toLocaleString()}</td>
                  <td className={`py-2.5 text-right font-bold ${s.total_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {s.total_return_pct >= 0 ? '+' : ''}{s.total_return_pct.toFixed(2)}%
                  </td>
                  <td className="py-2.5 text-right text-slate-400">{s.benchmark_return_pct.toFixed(2)}%</td>
                  <td className={`py-2.5 text-right ${s.alpha_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {s.alpha_pct >= 0 ? '+' : ''}{s.alpha_pct.toFixed(2)}%
                  </td>
                  <td className="py-2.5 text-right text-rose-400">-{s.max_drawdown_pct.toFixed(2)}%</td>
                  <td className="py-2.5 text-right text-slate-300">{s.trades}</td>
                  <td className="py-2.5 text-right text-cyan-300">
                    {s.win_rate_pct != null ? `${s.win_rate_pct.toFixed(1)}%` : 'N/A'}
                  </td>
                  <td className="py-2.5 text-right text-purple-300">{s.sharpe_ratio}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Historical Simulated Trades Log */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-amber-400" />
            <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
              Historical Backtest Execution Log (Friction Modeled)
            </h4>
          </div>
          <span className="text-xs font-mono text-slate-400">Total Trades: {trades.length}</span>
        </div>

        {trades.length === 0 ? (
          <div className="py-8 text-center text-slate-500 text-xs italic">
            No executed trades recorded for this strategy configuration.
          </div>
        ) : (
          <div className="overflow-x-auto max-h-64 overflow-y-auto">
            <table className="w-full text-xs font-mono text-left">
              <thead className="sticky top-0 bg-slate-900 border-b border-slate-800 text-slate-400">
                <tr>
                  <th className="pb-2">Trade #</th>
                  <th className="pb-2">Side</th>
                  <th className="pb-2">Split</th>
                  <th className="pb-2 text-right">Entry Price</th>
                  <th className="pb-2 text-right">Exit Price</th>
                  <th className="pb-2 text-right">Qty</th>
                  <th className="pb-2 text-right">PnL ($)</th>
                  <th className="pb-2 text-right">PnL (%)</th>
                  <th className="pb-2 text-right">Fees ($)</th>
                  <th className="pb-2 text-right">Holding Bars</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {trades.map((t) => (
                  <tr key={`${t.trade_id}-${t.split}-${t.entry_bar}`}>
                    <td className="py-2 text-slate-400">#{t.trade_id}</td>
                    <td className="py-2">
                      <span className="bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded text-[10px]">
                        {t.side}
                      </span>
                    </td>
                    <td className="py-2 text-slate-400 text-[11px]">{t.split}</td>
                    <td className="py-2 text-right">${t.entry_price.toFixed(2)}</td>
                    <td className="py-2 text-right">${t.exit_price.toFixed(2)}</td>
                    <td className="py-2 text-right">{t.qty.toFixed(4)}</td>
                    <td className={`py-2 text-right font-bold ${t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)}
                    </td>
                    <td className={`py-2 text-right ${t.pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%
                    </td>
                    <td className="py-2 text-right text-slate-400">${t.fees.toFixed(2)}</td>
                    <td className="py-2 text-right text-slate-400">{t.holding_bars}m</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
