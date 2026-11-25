import React, { useEffect, useRef, useState, useMemo } from 'react'
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createSeriesMarkers,
  ColorType,
  CrosshairMode,
} from 'lightweight-charts'
import type {
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
} from 'lightweight-charts'
import type { Candle, TradingSignal, Timeframe } from '../types'
import { Eye, EyeOff, Navigation, AlertTriangle } from 'lucide-react'

interface TradingChartProps {
  candles: Candle[]
  signals: TradingSignal[]
  symbol: string
  timeframe: Timeframe
  onSelectTimeframe: (tf: Timeframe) => void
  onSelectSignal: (signal: TradingSignal) => void
}

export const TradingChart: React.FC<TradingChartProps> = ({
  candles,
  signals,
  symbol,
  timeframe,
  onSelectTimeframe,
  onSelectSignal,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const sma20SeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const sma50SeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const markersControllerRef = useRef<any>(null)

  // Toggles
  const [showSMA20, setShowSMA20] = useState(true)
  const [showSMA50, setShowSMA50] = useState(true)
  const [autoScroll, setAutoScroll] = useState(true)

  // Hover Tooltip State
  const [hoverData, setHoverData] = useState<{
    time: string
    open: number
    high: number
    low: number
    close: number
    volume: number
    change: number
    changePercent: number
  } | null>(null)

  // Clean, sort, and deduplicate candles by time
  const processedCandles = useMemo(() => {
    if (!candles || candles.length === 0) return []
    const sorted = [...candles].sort((a, b) => a.time - b.time)
    const deduped: Candle[] = []
    for (const c of sorted) {
      if (deduped.length > 0 && deduped[deduped.length - 1].time === c.time) {
        deduped[deduped.length - 1] = c
      } else {
        deduped.push(c)
      }
    }
    return deduped
  }, [candles])

  // Compute SMAs client-side for dynamic timeframe responsiveness
  const sma20Data = useMemo(() => {
    if (processedCandles.length < 20) return []
    const points = []
    let sum = 0
    for (let i = 0; i < processedCandles.length; i++) {
      sum += processedCandles[i].close
      if (i >= 20) {
        sum -= processedCandles[i - 20].close
      }
      if (i >= 19) {
        points.push({
          time: processedCandles[i].time as UTCTimestamp,
          value: Number((sum / 20).toFixed(2)),
        })
      }
    }
    return points
  }, [processedCandles])

  const sma50Data = useMemo(() => {
    if (processedCandles.length < 50) return []
    const points = []
    let sum = 0
    for (let i = 0; i < processedCandles.length; i++) {
      sum += processedCandles[i].close
      if (i >= 50) {
        sum -= processedCandles[i - 50].close
      }
      if (i >= 49) {
        points.push({
          time: processedCandles[i].time as UTCTimestamp,
          value: Number((sum / 50).toFixed(2)),
        })
      }
    }
    return points
  }, [processedCandles])

  // Format markers from trading signals matching candle timestamps
  const chartMarkers = useMemo(() => {
    if (!processedCandles.length || !signals.length) return []
    const candleTimes = processedCandles.map((c) => c.time)

    return signals
      .filter((s) => s.symbol === symbol)
      .map((s) => {
        const sigTime = s.event_time || Math.floor(new Date(s.timestamp).getTime() / 1000)
        let matchedTime = candleTimes[candleTimes.length - 1]
        for (let i = 0; i < candleTimes.length; i++) {
          if (candleTimes[i] >= sigTime) {
            matchedTime = candleTimes[i]
            break
          }
        }

        const isBuy = s.signal === 'BUY'
        const priceLabel = s.price != null ? `$${s.price.toFixed(2)}` : 'Market'
        return {
          time: matchedTime as UTCTimestamp,
          position: isBuy ? ('belowBar' as const) : ('aboveBar' as const),
          color: isBuy ? '#10b981' : '#ef4444',
          shape: isBuy ? ('arrowUp' as const) : ('arrowDown' as const),
          text: `${s.signal} @ ${priceLabel}`,
          id: s.id,
        }
      })
      .sort((a, b) => (a.time as number) - (b.time as number))
  }, [processedCandles, signals, symbol])

  // Initialize Lightweight Chart
  useEffect(() => {
    if (!chartContainerRef.current) return

    const container = chartContainerRef.current
    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: '#090d16' },
        textColor: '#94a3b8',
        fontSize: 12,
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      },
      grid: {
        vertLines: { color: 'rgba(30, 41, 59, 0.5)' },
        horzLines: { color: 'rgba(30, 41, 59, 0.5)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: '#64748b',
          width: 1,
          style: 2,
          labelBackgroundColor: '#1e293b',
        },
        horzLine: {
          color: '#64748b',
          width: 1,
          style: 2,
          labelBackgroundColor: '#1e293b',
        },
      },
      rightPriceScale: {
        borderColor: '#1e293b',
        scaleMargins: {
          top: 0.1,
          bottom: 0.25,
        },
      },
      timeScale: {
        borderColor: '#1e293b',
        timeVisible: true,
        secondsVisible: false,
      },
    })

    // Candlestick Series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: true,
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    })

    // Volume Histogram Series
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: 'volume',
    })

    chart.priceScale('volume').applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    })

    // SMA 20 Line Series (Cyan)
    const sma20Series = chart.addSeries(LineSeries, {
      color: '#06b6d4',
      lineWidth: 2,
      title: 'SMA 20',
      priceLineVisible: false,
    })

    // SMA 50 Line Series (Orange)
    const sma50Series = chart.addSeries(LineSeries, {
      color: '#f97316',
      lineWidth: 2,
      title: 'SMA 50',
      priceLineVisible: false,
    })

    // Crosshair move listener for Tooltip
    chart.subscribeCrosshairMove((param) => {
      if (
        param.point === undefined ||
        !param.time ||
        param.point.x < 0 ||
        param.point.x > container.clientWidth ||
        param.point.y < 0 ||
        param.point.y > container.clientHeight
      ) {
        setHoverData(null)
      } else {
        const cData = param.seriesData.get(candleSeries) as any
        const vData = param.seriesData.get(volumeSeries) as any
        if (cData) {
          const dateStr = new Date((param.time as number) * 1000).toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          })
          const change = cData.close - cData.open
          const changePercent = (change / cData.open) * 100
          setHoverData({
            time: dateStr,
            open: cData.open,
            high: cData.high,
            low: cData.low,
            close: cData.close,
            volume: vData?.value || 0,
            change,
            changePercent,
          })
        }
      }
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries
    sma20SeriesRef.current = sma20Series
    sma50SeriesRef.current = sma50Series

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      sma20SeriesRef.current = null
      sma50SeriesRef.current = null
      markersControllerRef.current = null
    }
  }, [])

  // Update Candle & Volume Data
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return

    const candleData = processedCandles.map((c) => ({
      time: c.time as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))

    const volData = processedCandles.map((c) => ({
      time: c.time as UTCTimestamp,
      value: c.volume,
      color: c.close >= c.open ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)',
    }))

    candleSeriesRef.current.setData(candleData)
    volumeSeriesRef.current.setData(volData)

    if (autoScroll && chartRef.current && candleData.length > 0) {
      chartRef.current.timeScale().scrollToRealTime()
    }
  }, [processedCandles, autoScroll])

  // Update SMA Series
  useEffect(() => {
    if (!sma20SeriesRef.current || !sma50SeriesRef.current) return

    if (showSMA20 && sma20Data.length > 0) {
      sma20SeriesRef.current.applyOptions({ visible: true })
      sma20SeriesRef.current.setData(sma20Data)
    } else {
      sma20SeriesRef.current.applyOptions({ visible: false })
      sma20SeriesRef.current.setData([])
    }

    if (showSMA50 && sma50Data.length > 0) {
      sma50SeriesRef.current.applyOptions({ visible: true })
      sma50SeriesRef.current.setData(sma50Data)
    } else {
      sma50SeriesRef.current.applyOptions({ visible: false })
      sma50SeriesRef.current.setData([])
    }
  }, [showSMA20, showSMA50, sma20Data, sma50Data])

  // Update Signal Markers using createSeriesMarkers
  useEffect(() => {
    if (!candleSeriesRef.current) return

    try {
      if (!markersControllerRef.current) {
        markersControllerRef.current = createSeriesMarkers(
          candleSeriesRef.current,
          chartMarkers
        )
      } else {
        markersControllerRef.current.setMarkers(chartMarkers)
      }
    } catch (err) {
      console.warn('Marker rendering update:', err)
    }
  }, [chartMarkers])

  const latestCandle = processedCandles[processedCandles.length - 1]

  return (
    <div className="relative flex flex-col h-full bg-slate-950 rounded-xl border border-slate-800 overflow-hidden shadow-2xl">
      {/* Top Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2 bg-slate-900/80 border-b border-slate-800 text-xs">
        {/* Left: Timeframe selectors & OHLCV Quick Stats */}
        <div className="flex items-center gap-3">
          <div className="flex bg-slate-950 p-0.5 rounded border border-slate-800">
            {(['1m', '5m', '15m', '1h'] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => onSelectTimeframe(tf)}
                className={`px-2 py-0.5 rounded text-[11px] font-bold transition-colors ${
                  timeframe === tf
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Indicator toggles */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowSMA20(!showSMA20)}
              className={`flex items-center gap-1 px-2 py-0.5 rounded border font-mono text-[11px] transition-colors ${
                showSMA20
                  ? 'bg-cyan-950/60 text-cyan-300 border-cyan-700/60'
                  : 'bg-slate-900 text-slate-500 border-slate-800'
              }`}
              title="Toggle Simple Moving Average (20 bars)"
            >
              {showSMA20 ? <Eye className="w-3 h-3 text-cyan-400" /> : <EyeOff className="w-3 h-3" />}
              SMA 20
            </button>

            <button
              onClick={() => setShowSMA50(!showSMA50)}
              className={`flex items-center gap-1 px-2 py-0.5 rounded border font-mono text-[11px] transition-colors ${
                showSMA50
                  ? 'bg-amber-950/60 text-amber-300 border-amber-700/60'
                  : 'bg-slate-900 text-slate-500 border-slate-800'
              }`}
              title="Toggle Simple Moving Average (50 bars)"
            >
              {showSMA50 ? <Eye className="w-3 h-3 text-amber-400" /> : <EyeOff className="w-3 h-3" />}
              SMA 50
            </button>
          </div>
        </div>

        {/* Right: Auto-scroll & Signals count */}
        <div className="flex items-center gap-2">
          {processedCandles.length < 50 && (
            <div className="flex items-center gap-1 text-[11px] text-amber-400 bg-amber-950/40 px-2 py-0.5 rounded border border-amber-800/40">
              <AlertTriangle className="w-3 h-3" />
              <span>{processedCandles.length < 20 ? 'SMA 20/50 insufficient bars' : 'SMA 50 warming up'}</span>
            </div>
          )}

          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded border font-mono text-[11px] transition-colors ${
              autoScroll
                ? 'bg-emerald-950/60 text-emerald-300 border-emerald-700/60'
                : 'bg-slate-900 text-slate-400 border-slate-800'
            }`}
            title="Toggle Auto-Scroll to Real-Time"
          >
            <Navigation className="w-3 h-3" />
            {autoScroll ? 'Auto-Scroll ON' : 'Auto-Scroll OFF'}
          </button>
        </div>
      </div>

      {/* OHLCV Header Overlay */}
      <div className="px-4 py-1.5 bg-slate-950/80 border-b border-slate-900 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono">
        <span className="font-bold text-slate-200">{symbol}</span>
        {hoverData ? (
          <>
            <span className="text-slate-500">{hoverData.time}</span>
            <span className="text-slate-400">O: <strong className="text-slate-200">${hoverData.open.toFixed(2)}</strong></span>
            <span className="text-slate-400">H: <strong className="text-emerald-400">${hoverData.high.toFixed(2)}</strong></span>
            <span className="text-slate-400">L: <strong className="text-rose-400">${hoverData.low.toFixed(2)}</strong></span>
            <span className="text-slate-400">C: <strong className="text-slate-200">${hoverData.close.toFixed(2)}</strong></span>
            <span className="text-slate-400">V: <strong className="text-blue-400">{hoverData.volume.toLocaleString()}</strong></span>
            <span className={hoverData.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
              {hoverData.change >= 0 ? '+' : ''}{hoverData.change.toFixed(2)} ({hoverData.changePercent.toFixed(2)}%)
            </span>
          </>
        ) : latestCandle ? (
          <>
            <span className="text-slate-500">
              {new Date(latestCandle.time * 1000).toLocaleString('en-US', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
            <span className="text-slate-400">O: <strong className="text-slate-200">${latestCandle.open.toFixed(2)}</strong></span>
            <span className="text-slate-400">H: <strong className="text-emerald-400">${latestCandle.high.toFixed(2)}</strong></span>
            <span className="text-slate-400">L: <strong className="text-rose-400">${latestCandle.low.toFixed(2)}</strong></span>
            <span className="text-slate-400">C: <strong className="text-slate-200">${latestCandle.close.toFixed(2)}</strong></span>
            <span className="text-slate-400">V: <strong className="text-blue-400">{latestCandle.volume.toLocaleString()}</strong></span>
          </>
        ) : (
          <span className="text-slate-500 italic">Awaiting price data...</span>
        )}

        {/* Signals Quick Pill */}
        {chartMarkers.length > 0 && (
          <div className="ml-auto flex items-center gap-1.5">
            <span className="text-[10px] text-slate-400">Signals:</span>
            {chartMarkers.slice(-3).map((m) => (
              <button
                key={m.id}
                onClick={() => {
                  const target = signals.find((s) => s.id === m.id)
                  if (target) onSelectSignal(target)
                }}
                className={`text-[10px] px-1.5 py-0.2 rounded font-semibold transition-transform hover:scale-105 ${
                  m.shape === 'arrowUp'
                    ? 'bg-emerald-950/70 text-emerald-300 border border-emerald-700/50'
                    : 'bg-rose-950/70 text-rose-300 border border-rose-700/50'
                }`}
              >
                {m.shape === 'arrowUp' ? '▲ BUY' : '▼ SELL'}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Main Chart Canvas Container */}
      <div ref={chartContainerRef} className="flex-1 w-full min-h-[420px]" />
    </div>
  )
}
