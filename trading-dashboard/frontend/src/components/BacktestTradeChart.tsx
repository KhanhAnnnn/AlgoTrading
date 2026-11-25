import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  createSeriesMarkers,
  ColorType,
  CrosshairMode,
  PriceScaleMode,
} from 'lightweight-charts'
import type {
  IChartApi,
  ISeriesApi,
  SeriesMarker,
  UTCTimestamp,
} from 'lightweight-charts'
import type {
  BacktestChartBundle,
  BacktestSimulatedFill,
  BacktestStrategySignal,
  BacktestClosedTrade,
} from '../types'
import {
  Eye,
  EyeOff,
  Maximize2,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
  Info,
  X,
  Clock,
} from 'lucide-react'

export interface ChartFocusRequest {
  epoch: number
  endEpoch?: number
  fillId?: string
  tradeId?: string
  nonce: number
}

interface BacktestTradeChartProps {
  bundle: BacktestChartBundle
  activeSymbol: string
  filteredFills: BacktestSimulatedFill[]
  selectedFillId: string | null
  focusRequest: ChartFocusRequest | null
  onSelectFill: (fill: BacktestSimulatedFill) => void
}

interface HoveredBarSnapshot {
  time: number
  timestamp: string
  session?: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  is_warmup: boolean
  maFast: number | null
  maSlow: number | null
  rsi: number | null
  fills: BacktestSimulatedFill[]
  signals: BacktestStrategySignal[]
  closedTrades: BacktestClosedTrade[]
}

type ChartTzMode = 'NY' | 'UTC'

const nyFullFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/New_York',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

const nyTickFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

function formatChartTime(epochSec: number, tzMode: ChartTzMode): string {
  const d = new Date(epochSec * 1000)
  if (tzMode === 'UTC') {
    return d.toISOString().replace('T', ' ').slice(0, 16) + ' UTC'
  }
  return nyFullFormatter.format(d).replace(',', '') + ' ET'
}

function formatAxisTick(epochSec: number, tzMode: ChartTzMode): string {
  const d = new Date(epochSec * 1000)
  if (tzMode === 'UTC') {
    return d.toISOString().slice(5, 16).replace('T', ' ')
  }
  return nyTickFormatter.format(d).replace(',', '')
}

function formatCompactWindowIso(iso?: string | null, tzMode: ChartTzMode = 'NY'): string {
  if (!iso) return 'N/A'
  const ms = Date.parse(iso)
  if (Number.isNaN(ms)) return iso
  return formatChartTime(Math.floor(ms / 1000), tzMode)
}

export const BacktestTradeChart: React.FC<BacktestTradeChartProps> = React.memo(({
  bundle,
  activeSymbol,
  filteredFills,
  selectedFillId,
  focusRequest,
  onSelectFill,
}) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const sessionBreakSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const maFastSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const maSlowSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const rsiSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const markersCtrlRef = useRef<any>(null)

  const lastHoverEpochRef = useRef<number | null>(null)
  const hoverRafRef = useRef<number | null>(null)
  const resizeRafRef = useRef<number | null>(null)
  const lastBoxSizeRef = useRef<{ w: number; h: number }>({ w: 0, h: 0 })
  const lastHandledFocusNonceRef = useRef<number | null>(null)
  const telemetryRef = useRef({
    createCount: 0,
    disposeCount: 0,
    fitContentCount: 0,
    resizeApplyCount: 0,
    crosshairStateUpdates: 0,
    hoverIgnoredSameBar: 0,
  })

  const isCryptoSymbol = (activeSymbol || bundle.symbols[0] || '').includes('/')
  const isRsiPrimary = (bundle.config?.strategy_id || bundle.indicators?.strategy_id || '').toUpperCase().includes('RSI')
  const [showMA, setShowMA] = useState<boolean>(!isRsiPrimary)
  const [showRSI, setShowRSI] = useState<boolean>(true)
  const [showSignals, setShowSignals] = useState<boolean>(false)
  const [showExecutions, setShowExecutions] = useState<boolean>(true)
  const [showVolume, setShowVolume] = useState<boolean>(true)
  const [volumeLogScale, setVolumeLogScale] = useState<boolean>(true)
  const [showSessionBreaks, setShowSessionBreaks] = useState<boolean>(true)
  const [tzMode, setTzMode] = useState<ChartTzMode>(isCryptoSymbol ? 'UTC' : 'NY')

  const [hovered, setHovered] = useState<HoveredBarSnapshot | null>(null)
  const [pinnedEpoch, setPinnedEpoch] = useState<number | null>(null)

  const params = bundle.indicators?.params || {
    fast_period: 20,
    slow_period: 50,
    rsi_period: 14,
    rsi_method: 'SIMPLE_ROLLING',
    rsi_oversold: 30,
    rsi_overbought: 70,
  }

  // Filter candles for activeSymbol, sorted chronologically & deduplicated by UTC epoch
  const candles = useMemo(() => {
    const raw = (bundle.candles || []).filter((c) => !activeSymbol || c.symbol === activeSymbol)
    const sorted = [...raw].sort((a, b) => a.time - b.time)
    const out: typeof sorted = []
    for (const c of sorted) {
      if (out.length > 0 && out[out.length - 1].time === c.time) {
        out[out.length - 1] = c
      } else {
        out.push(c)
      }
    }
    return out
  }, [bundle.candles, activeSymbol])

  const symbolIndicators = useMemo(() => {
    const bySym = bundle.indicators?.series_by_symbol || {}
    return bySym[activeSymbol] || Object.values(bySym)[0] || { ma_fast: [], ma_slow: [], rsi: [] }
  }, [bundle.indicators, activeSymbol])

  const priceFormat = useMemo(() => {
    if (candles.length === 0) return { precision: 2, minMove: 0.01 }
    const mid = candles[Math.floor(candles.length / 2)].close
    if (mid < 1) return { precision: 5, minMove: 0.00001 }
    if (mid < 10) return { precision: 4, minMove: 0.0001 }
    if (mid < 100) return { precision: 3, minMove: 0.001 }
    return { precision: 2, minMove: 0.01 }
  }, [candles])

  // Lookup maps keyed by candle epoch
  const barLookup = useMemo(() => {
    const cMap = new Map<number, (typeof candles)[0]>()
    candles.forEach((c) => cMap.set(c.time, c))

    const fastMap = new Map<number, number | null>()
    ;(symbolIndicators.ma_fast || []).forEach((p) => fastMap.set(p.time, p.value))

    const slowMap = new Map<number, number | null>()
    ;(symbolIndicators.ma_slow || []).forEach((p) => slowMap.set(p.time, p.value))

    const rsiMap = new Map<number, number | null>()
    ;(symbolIndicators.rsi || []).forEach((p) => rsiMap.set(p.time, p.value))

    const fillMap = new Map<number, BacktestSimulatedFill[]>()
    const candleTimes = candles.map((c) => c.time)

    const resolveEpoch = (rawEpoch?: number, iso?: string): number | null => {
      const target = rawEpoch ?? (iso ? Math.floor(new Date(iso).getTime() / 1000) : 0)
      if (!target || candleTimes.length === 0) return null
      if (cMap.has(target)) return target
      // Binary search nearest candle >= target if bar aligns slightly differently
      let lo = 0
      let hi = candleTimes.length - 1
      while (lo < hi) {
        const mid = (lo + hi) >> 1
        if (candleTimes[mid] < target) lo = mid + 1
        else hi = mid
      }
      return candleTimes[lo]
    }

    filteredFills
      .filter((f) => !activeSymbol || f.symbol === activeSymbol)
      .forEach((f) => {
        const ep = resolveEpoch(f.fill_epoch, f.fill_time)
        if (ep !== null) {
          const list = fillMap.get(ep) || []
          list.push(f)
          fillMap.set(ep, list)
        }
      })

    const sigMap = new Map<number, BacktestStrategySignal[]>()
    ;(bundle.signals || [])
      .filter((s) => !activeSymbol || s.symbol === activeSymbol)
      .forEach((s) => {
        const ep = resolveEpoch(s.time, s.timestamp)
        if (ep !== null) {
          const list = sigMap.get(ep) || []
          list.push(s)
          sigMap.set(ep, list)
        }
      })

    const tradeByExitEpoch = new Map<number, BacktestClosedTrade[]>()
    const tradeByFillId = new Map<string, BacktestClosedTrade>()
    ;(bundle.closed_trades || [])
      .filter((t) => !activeSymbol || t.symbol === activeSymbol)
      .forEach((t) => {
        const list = tradeByExitEpoch.get(t.exit_epoch) || []
        list.push(t)
        tradeByExitEpoch.set(t.exit_epoch, list)
        tradeByFillId.set(t.exit_fill_id, t)
        t.entry_fill_ids.forEach((id) => tradeByFillId.set(id, t))
      })

    return { cMap, fastMap, slowMap, rsiMap, fillMap, sigMap, tradeByExitEpoch, tradeByFillId, resolveEpoch }
  }, [candles, symbolIndicators, filteredFills, bundle.signals, bundle.closed_trades, activeSymbol])

  // Construct Lightweight Charts Markers distinguishing Execution Arrows vs Signal Circles
  const allMarkers = useMemo(() => {
    const markers: SeriesMarker<UTCTimestamp>[] = []

    if (showSignals) {
      barLookup.sigMap.forEach((sigs, epoch) => {
        const candle = barLookup.cMap.get(epoch)
        if (candle?.is_warmup) return // strictly zero signal markers in warmup
        sigs.forEach((sig) => {
          if (sig.signal_type !== 'BUY' && sig.signal_type !== 'SELL') return
          const isBuy = sig.signal_type === 'BUY'
          markers.push({
            time: epoch as UTCTimestamp,
            position: isBuy ? 'belowBar' : 'aboveBar',
            color: sig.decision_status === 'REJECTED' ? '#64748b' : isBuy ? '#38bdf8' : '#fb923c',
            shape: 'circle',
            size: 1,
            // Omit verbose text to prevent adjacent 1m label collisions; full signal info appears on hover/click
            id: `sig_${sig.signal_id}`,
          })
        })
      })
    }

    if (showExecutions) {
      barLookup.fillMap.forEach((fillsAtBar, epoch) => {
        const candle = barLookup.cMap.get(epoch)
        if (candle?.is_warmup) return // never display fills inside warmup
        // Group same-timestamp, same-side, same-price fills while preserving every distinct execution price & side
        const buckets = new Map<string, BacktestSimulatedFill[]>()
        fillsAtBar.forEach((f) => {
          const key = `${f.side.toUpperCase()}_${f.fill_price.toFixed(4)}`
          const arr = buckets.get(key) || []
          arr.push(f)
          buckets.set(key, arr)
        })

        buckets.forEach((bucket) => {
          const first = bucket[0]
          const isBuy = first.side.toUpperCase() === 'BUY'
          const hasSelected = selectedFillId ? bucket.some((f) => f.simulated_fill_id === selectedFillId) : false
          const isPartial = bucket.some((f) => f.is_partial_fill)

          const compactLabel = isBuy
            ? (bucket.length > 1 ? `B×${bucket.length}` : isPartial ? 'B(P)' : 'B')
            : (bucket.length > 1 ? `S×${bucket.length}` : isPartial ? 'S(P)' : 'S')

          markers.push({
            time: epoch as UTCTimestamp,
            position: isBuy ? 'atPriceBottom' : 'atPriceTop',
            price: first.fill_price,
            color: hasSelected ? '#facc15' : isBuy ? '#10b981' : '#ef4444',
            shape: isBuy ? 'arrowUp' : 'arrowDown',
            size: hasSelected ? 2 : 1,
            text: hasSelected ? `${compactLabel} @$${first.fill_price.toFixed(2)}` : compactLabel,
            id: `fill_${first.simulated_fill_id}`,
          })
        })
      })
    }

    markers.sort((a, b) => (a.time as number) - (b.time as number))
    return markers
  }, [barLookup, showSignals, showExecutions, selectedFillId])

  // Build snapshot helper
  const getSnapshotForEpoch = (epoch: number): HoveredBarSnapshot | null => {
    const c = barLookup.cMap.get(epoch)
    if (!c) return null
    return {
      time: epoch,
      timestamp: c.timestamp,
      session: c.session,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume,
      is_warmup: c.is_warmup,
      maFast: barLookup.fastMap.get(epoch) ?? null,
      maSlow: barLookup.slowMap.get(epoch) ?? null,
      rsi: barLookup.rsiMap.get(epoch) ?? null,
      fills: barLookup.fillMap.get(epoch) || [],
      signals: barLookup.sigMap.get(epoch) || [],
      closedTrades: barLookup.tradeByExitEpoch.get(epoch) || [],
    }
  }

  // Initialize Multi-Pane Lightweight Chart
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight || 540,
      layout: {
        background: { type: ColorType.Solid, color: '#070b14' },
        textColor: '#94a3b8',
        fontSize: 11,
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      },
      grid: {
        vertLines: { color: 'rgba(30, 41, 59, 0.45)' },
        horzLines: { color: 'rgba(30, 41, 59, 0.45)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#64748b', style: 2, labelBackgroundColor: '#1e293b' },
        horzLine: { color: '#64748b', style: 2, labelBackgroundColor: '#1e293b' },
      },
      localization: {
        timeFormatter: (time: any) => formatChartTime(Number(time), tzMode),
      },
      rightPriceScale: {
        borderColor: '#1e293b',
        scaleMargins: { top: 0.08, bottom: 0.22 },
      },
      timeScale: {
        borderColor: '#1e293b',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 6,
        tickMarkFormatter: (time: any) => formatAxisTick(Number(time), tzMode),
      },
    })

    // Pane 0: Candlestick + Volume + Session-Break Hairlines + MA Fast + MA Slow
    const sessionBreakSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: 'session_bg',
      lastValueVisible: false,
      priceLineVisible: false,
      base: 0,
    }, 0)
    chart.priceScale('session_bg', 0).applyOptions({
      visible: false,
      scaleMargins: { top: 0, bottom: 0 },
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: true,
      wickVisible: true,
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceFormat: { type: 'price', precision: priceFormat.precision, minMove: priceFormat.minMove },
    }, 0)

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: 'rgba(56, 189, 248, 0.25)',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    }, 0)
    chart.priceScale('volume', 0).applyOptions({
      mode: volumeLogScale ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal,
      scaleMargins: { top: 0.82, bottom: 0 },
    })

    const maFastSeries = chart.addSeries(LineSeries, {
      color: '#38bdf8',
      lineWidth: 2,
      title: `MA ${params.fast_period}`,
      crosshairMarkerVisible: true,
      priceFormat: { type: 'price', precision: priceFormat.precision, minMove: priceFormat.minMove },
    }, 0)

    const maSlowSeries = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 2,
      title: `MA ${params.slow_period}`,
      crosshairMarkerVisible: true,
      priceFormat: { type: 'price', precision: priceFormat.precision, minMove: priceFormat.minMove },
    }, 0)

    // Pane 1: Synchronized RSI 14 (0-100 scale)
    const rsiSeries = chart.addSeries(LineSeries, {
      color: '#a855f7',
      lineWidth: 2,
      title: `RSI ${params.rsi_period}`,
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: 0, maxValue: 100 },
      }),
    }, 1)

    rsiSeries.createPriceLine({
      price: params.rsi_overbought ?? 70,
      color: 'rgba(239, 68, 68, 0.55)',
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: `OB (${params.rsi_overbought ?? 70})`,
    })
    rsiSeries.createPriceLine({
      price: params.rsi_oversold ?? 30,
      color: 'rgba(16, 185, 129, 0.55)',
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: `OS (${params.rsi_oversold ?? 30})`,
    })

    // Allocate 72% height to Price Pane 0 and 28% height to RSI Pane 1
    try {
      const panes = chart.panes()
      if (panes.length >= 2) {
        panes[0].setStretchFactor(3)
        panes[1].setStretchFactor(1)
      }
    } catch {
      // Fallback safely if pane sizing isn't supported
    }

    const markersCtrl = createSeriesMarkers(candleSeries, [])

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries
    sessionBreakSeriesRef.current = sessionBreakSeries
    maFastSeriesRef.current = maFastSeries
    maSlowSeriesRef.current = maSlowSeries
    rsiSeriesRef.current = rsiSeries
    markersCtrlRef.current = markersCtrl

    telemetryRef.current.createCount += 1
    lastBoxSizeRef.current = {
      w: Math.round(container.clientWidth),
      h: Math.round(container.clientHeight || 540),
    }
    if (typeof window !== 'undefined') {
      ;(window as any).__backtestChartTelemetry = {
        getStats: () => ({ ...telemetryRef.current }),
        getVisibleLogicalRange: () => chartRef.current?.timeScale().getVisibleLogicalRange() ?? null,
        getVisibleRange: () => chartRef.current?.timeScale().getVisibleRange() ?? null,
      }
    }

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[entries.length - 1]
      if (!entry) return
      const w = Math.round(entry.contentRect.width)
      const h = Math.round(entry.contentRect.height)
      if (w <= 0 || h <= 0) return
      if (w === lastBoxSizeRef.current.w && h === lastBoxSizeRef.current.h) return
      lastBoxSizeRef.current = { w, h }
      if (resizeRafRef.current !== null) cancelAnimationFrame(resizeRafRef.current)
      resizeRafRef.current = requestAnimationFrame(() => {
        resizeRafRef.current = null
        telemetryRef.current.resizeApplyCount += 1
        chart.applyOptions({ width: w, height: h })
      })
    })
    resizeObserver.observe(container)

    return () => {
      if (hoverRafRef.current !== null) cancelAnimationFrame(hoverRafRef.current)
      if (resizeRafRef.current !== null) cancelAnimationFrame(resizeRafRef.current)
      resizeObserver.disconnect()
      chart.remove()
      telemetryRef.current.disposeCount += 1
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      sessionBreakSeriesRef.current = null
      maFastSeriesRef.current = null
      maSlowSeriesRef.current = null
      rsiSeriesRef.current = null
      markersCtrlRef.current = null
    }
  }, [bundle.run_id, activeSymbol, params.fast_period, params.slow_period, params.rsi_period, params.rsi_overbought, params.rsi_oversold, priceFormat.precision, priceFormat.minMove])

  // Subscribe to crosshair & click events with RAF coalescing + bar deduplication (0 hover jitter)
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    const onCrosshair = (param: any) => {
      const nextEpoch = param && param.time ? Number(param.time) : null
      if (nextEpoch === lastHoverEpochRef.current) {
        telemetryRef.current.hoverIgnoredSameBar += 1
        return
      }
      lastHoverEpochRef.current = nextEpoch

      if (hoverRafRef.current !== null) cancelAnimationFrame(hoverRafRef.current)
      hoverRafRef.current = requestAnimationFrame(() => {
        hoverRafRef.current = null
        telemetryRef.current.crosshairStateUpdates += 1
        if (nextEpoch === null) {
          setHovered(null)
        } else {
          setHovered(getSnapshotForEpoch(nextEpoch))
        }
      })
    }

    const onClick = (param: any) => {
      if (!param || !param.time) return
      const epoch = Number(param.time)
      const fillsAtBar = barLookup.fillMap.get(epoch)
      if (fillsAtBar && fillsAtBar.length > 0) {
        setPinnedEpoch(epoch)
        onSelectFill(fillsAtBar[0])
      } else {
        setPinnedEpoch(null)
      }
    }

    chart.subscribeCrosshairMove(onCrosshair)
    chart.subscribeClick(onClick)
    return () => {
      if (hoverRafRef.current !== null) cancelAnimationFrame(hoverRafRef.current)
      chart.unsubscribeCrosshairMove(onCrosshair)
      chart.unsubscribeClick(onClick)
    }
  }, [barLookup, onSelectFill])

  // Populate series data
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || !maFastSeriesRef.current || !maSlowSeriesRef.current || !rsiSeriesRef.current) {
      return
    }

    candleSeriesRef.current.setData(
      candles.map((c) => {
        const isUp = c.close >= c.open
        const isExtended = c.session === 'PRE_MARKET' || c.session === 'AFTER_HOURS'
        const isFlat = c.high === c.low
        const baseColor = isUp ? '#10b981' : '#ef4444'
        const bodyColor = c.is_warmup
          ? (isUp ? 'rgba(16, 185, 129, 0.38)' : 'rgba(239, 68, 68, 0.38)')
          : isExtended
          ? (isUp ? 'rgba(16, 185, 129, 0.48)' : 'rgba(239, 68, 68, 0.48)')
          : baseColor
        const borderColor = isExtended ? 'rgba(148, 163, 184, 0.75)' : (isFlat ? baseColor : bodyColor)
        return {
          time: c.time as UTCTimestamp,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
          color: bodyColor,
          borderColor,
          wickColor: isExtended ? 'rgba(148, 163, 184, 0.7)' : baseColor,
        }
      })
    )

    if (sessionBreakSeriesRef.current) {
      const breakBars: Array<{ time: UTCTimestamp; value: number; color: string }> = []
      for (let idx = 1; idx < candles.length; idx++) {
        const gapSec = candles[idx].time - candles[idx - 1].time
        if (gapSec > 60) {
          breakBars.push({
            time: candles[idx].time as UTCTimestamp,
            value: 1,
            color: gapSec >= 3600 ? 'rgba(251, 191, 36, 0.14)' : 'rgba(148, 163, 184, 0.08)',
          })
        }
      }
      sessionBreakSeriesRef.current.setData(breakBars)
    }

    volumeSeriesRef.current.setData(
      candles.map((c) => ({
        time: c.time as UTCTimestamp,
        value: c.volume,
        color: c.close >= c.open ? 'rgba(16, 185, 129, 0.28)' : 'rgba(239, 68, 68, 0.28)',
      }))
    )

    // Use WhitespaceData ({ time }) when value is null so chart shows explicit insufficient-data gap
    maFastSeriesRef.current.setData(
      (symbolIndicators.ma_fast || []).map((p) =>
        p.value !== null && p.value !== undefined
          ? { time: p.time as UTCTimestamp, value: p.value }
          : { time: p.time as UTCTimestamp }
      )
    )

    maSlowSeriesRef.current.setData(
      (symbolIndicators.ma_slow || []).map((p) =>
        p.value !== null && p.value !== undefined
          ? { time: p.time as UTCTimestamp, value: p.value }
          : { time: p.time as UTCTimestamp }
      )
    )

    rsiSeriesRef.current.setData(
      (symbolIndicators.rsi || []).map((p) =>
        p.value !== null && p.value !== undefined
          ? { time: p.time as UTCTimestamp, value: p.value }
          : { time: p.time as UTCTimestamp }
      )
    )

    if (chartRef.current) {
      telemetryRef.current.fitContentCount += 1
      chartRef.current.timeScale().fitContent()
    }
  }, [candles, symbolIndicators])

  // Apply series visibility, volume scale mode & timezone formatting dynamically
  useEffect(() => {
    maFastSeriesRef.current?.applyOptions({ visible: showMA })
    maSlowSeriesRef.current?.applyOptions({ visible: showMA })
    volumeSeriesRef.current?.applyOptions({ visible: showVolume })
    sessionBreakSeriesRef.current?.applyOptions({ visible: showSessionBreaks })
    rsiSeriesRef.current?.applyOptions({ visible: showRSI })
    if (chartRef.current) {
      chartRef.current.priceScale('volume', 0).applyOptions({
        mode: volumeLogScale ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal,
        scaleMargins: { top: 0.82, bottom: 0 },
      })
      chartRef.current.applyOptions({
        localization: {
          timeFormatter: (time: any) => formatChartTime(Number(time), tzMode),
        },
        timeScale: {
          tickMarkFormatter: (time: any) => formatAxisTick(Number(time), tzMode),
        },
      })
      try {
        const panes = chartRef.current.panes()
        if (panes.length >= 2) {
          panes[1].setStretchFactor(showRSI ? 1 : 0.0001)
          panes[0].setStretchFactor(showRSI ? 3 : 10)
        }
      } catch {
        // Ignore if pane API unavailable
      }
    }
  }, [showMA, showVolume, showRSI, showSessionBreaks, volumeLogScale, tzMode])

  useEffect(() => {
    if (markersCtrlRef.current) {
      markersCtrlRef.current.setMarkers(allMarkers)
    }
  }, [allMarkers])

  // Bidirectional zoom when user clicks a fill or closed trade in the Explorer table (guarded by nonce)
  useEffect(() => {
    if (!focusRequest || !chartRef.current || candles.length === 0) return
    if (lastHandledFocusNonceRef.current === focusRequest.nonce) return
    lastHandledFocusNonceRef.current = focusRequest.nonce

    const targetStart = barLookup.resolveEpoch(focusRequest.epoch) ?? focusRequest.epoch
    const targetEnd = focusRequest.endEpoch
      ? (barLookup.resolveEpoch(focusRequest.endEpoch) ?? focusRequest.endEpoch)
      : targetStart

    const minTime = candles[0].time
    const maxTime = candles[candles.length - 1].time
    const spanPaddingSec = focusRequest.endEpoch ? 15 * 60 : 30 * 60

    const from = Math.max(minTime, targetStart - spanPaddingSec) as UTCTimestamp
    const to = Math.min(maxTime, targetEnd + spanPaddingSec) as UTCTimestamp

    if (from < to) {
      chartRef.current.timeScale().setVisibleRange({ from, to })
    }
    setPinnedEpoch(targetStart)
  }, [focusRequest, candles, barLookup])

  const activeInspection = hovered || (pinnedEpoch !== null ? getSnapshotForEpoch(pinnedEpoch) : null)
  const latestCandle = candles.length > 0 ? candles[candles.length - 1] : null
  const hudSnapshot = activeInspection || (latestCandle ? getSnapshotForEpoch(latestCandle.time) : null)

  const manifest = bundle.dataset_manifest
  const isReal = manifest && !manifest.is_synthetic
  const symGaps = (bundle.gaps || []).filter((g) => !activeSymbol || g.symbol === activeSymbol)
  const gapCount = symGaps.length
  const gapSummary = bundle.gap_summary
  const readiness = bundle.indicator_readiness?.[activeSymbol || bundle.symbols[0]] ||
    (bundle.indicator_readiness ? Object.values(bundle.indicator_readiness)[0] : undefined)
  const sessionPolicy = bundle.session_policy || bundle.requested_window?.session_policy || 'STRICT_HOURS'
  const rthCount = candles.filter((c) => c.session === 'RTH').length
  const extCount = candles.filter((c) => c.session === 'PRE_MARKET' || c.session === 'AFTER_HOURS').length

  if (candles.length === 0) {
    return (
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-10 text-center text-slate-400 text-xs">
        No OHLCV candles stored for this run ({activeSymbol}). Run a new Alpaca Historical backtest to inspect interactive candle charts.
      </div>
    )
  }

  return (
    <div className="bg-slate-900/95 border border-slate-800 rounded-xl overflow-hidden shadow-lg flex flex-col">
      {/* Chart Toolbar Header */}
      <div className="px-4 py-2.5 bg-slate-950/90 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-bold text-white text-sm font-mono">{activeSymbol || bundle.symbols[0]}</span>
          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[10px]">
            {bundle.timeframe || '1m'}
          </span>
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
            isReal
              ? 'bg-emerald-950/80 text-emerald-300 border-emerald-700/60'
              : 'bg-amber-950/80 text-amber-300 border-amber-700/60'
          }`}>
            {isReal ? `ALPACA ${manifest?.feed || 'IEX'}` : 'SYNTHETIC FIXTURE'}
          </span>
          <span className="px-2 py-0.5 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-800/60 text-[10px] font-bold">
            {bundle.environment || 'SIMULATION'} • {bundle.trading_mode || 'DRY_RUN'}
          </span>
          <span className="px-2 py-0.5 rounded bg-slate-800/90 text-slate-300 border border-slate-700 text-[10px] font-mono">
            {isCryptoSymbol ? '24/7 CRYPTO' : sessionPolicy === 'ALL_HOURS' ? 'ALL HOURS (EXT+RTH)' : 'RTH ONLY (09:30-16:00 ET)'}
          </span>
          {gapCount > 0 && (
            <span
              className="px-2 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-800/60 text-[10px] flex items-center gap-1"
              title={gapSummary
                ? `Uninterpolated missing intervals — Overnight/Closed: ${gapSummary.non_trading_session}, Ext-Hours No-Trade: ${gapSummary.extended_hours_no_trade}, RTH Gaps: ${gapSummary.rth_missing}`
                : 'Missing 1m intervals detected (session breaks/IEX gaps); no bars were fabricated or interpolated.'}
            >
              <AlertTriangle className="w-3 h-3" />
              {gapCount} Gap{gapCount > 1 ? 's' : ''} (Real / Uninterpolated)
            </span>
          )}
        </div>

        {/* Layer Toggles, Timezone, Volume Scale & Zoom Fit */}
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => setShowMA((v) => !v)}
            className={`px-2 py-1 rounded text-[11px] font-mono border flex items-center gap-1 transition ${
              showMA ? 'bg-sky-950/60 border-sky-700/70 text-sky-300' : 'bg-slate-900 border-slate-800 text-slate-500'
            }`}
          >
            {showMA ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
            MA {params.fast_period}/{params.slow_period}
          </button>

          <button
            type="button"
            onClick={() => setShowRSI((v) => !v)}
            className={`px-2 py-1 rounded text-[11px] font-mono border flex items-center gap-1 transition ${
              showRSI ? 'bg-purple-950/60 border-purple-700/70 text-purple-300' : 'bg-slate-900 border-slate-800 text-slate-500'
            }`}
          >
            <Activity className="w-3 h-3" />
            RSI {params.rsi_period}
          </button>

          <button
            type="button"
            onClick={() => setShowExecutions((v) => !v)}
            className={`px-2 py-1 rounded text-[11px] font-mono border transition ${
              showExecutions ? 'bg-emerald-950/60 border-emerald-700/70 text-emerald-300' : 'bg-slate-900 border-slate-800 text-slate-500'
            }`}
          >
            Fills ({filteredFills.length})
          </button>

          <button
            type="button"
            onClick={() => setShowSignals((v) => !v)}
            className={`px-2 py-1 rounded text-[11px] font-mono border transition ${
              showSignals ? 'bg-cyan-950/60 border-cyan-700/70 text-cyan-300' : 'bg-slate-900 border-slate-800 text-slate-500'
            }`}
            title="Show signal origin dots (off by default to reduce clutter)"
          >
            Signals
          </button>

          <button
            type="button"
            onClick={() => setShowVolume((v) => !v)}
            className={`px-2 py-1 rounded text-[11px] font-mono border transition ${
              showVolume ? 'bg-slate-800 border-slate-700 text-slate-200' : 'bg-slate-900 border-slate-800 text-slate-500'
            }`}
          >
            Vol
          </button>

          {showVolume && (
            <button
              type="button"
              onClick={() => setVolumeLogScale((v) => !v)}
              className={`px-2 py-1 rounded text-[11px] font-mono border transition ${
                volumeLogScale ? 'bg-indigo-950/70 border-indigo-700 text-indigo-300' : 'bg-slate-900 border-slate-700 text-slate-300'
              }`}
              title="Toggle Volume Log Scale so single open/close spikes do not squash normal bars"
            >
              {volumeLogScale ? 'Vol: Log' : 'Vol: Lin'}
            </button>
          )}

          <button
            type="button"
            onClick={() => setShowSessionBreaks((v) => !v)}
            className={`px-2 py-1 rounded text-[11px] font-mono border transition ${
              showSessionBreaks ? 'bg-amber-950/60 border-amber-700/60 text-amber-300' : 'bg-slate-900 border-slate-800 text-slate-500'
            }`}
            title="Highlight compressed overnight/no-trade gap boundaries without fabricating candles"
          >
            Breaks
          </button>

          <button
            type="button"
            onClick={() => setTzMode((m) => (m === 'NY' ? 'UTC' : 'NY'))}
            className="px-2 py-1 rounded text-[11px] font-mono border bg-slate-900 hover:bg-slate-800 border-slate-700 text-slate-200 flex items-center gap-1"
            title="Switch chart axis & HUD timezone between America/New_York (ET) and UTC"
          >
            <Clock className="w-3 h-3 text-sky-400" />
            {tzMode === 'NY' ? 'ET (NY)' : 'UTC'}
          </button>

          <button
            type="button"
            onClick={() => {
              setPinnedEpoch(null)
              chartRef.current?.timeScale().fitContent()
            }}
            className="px-2 py-1 rounded text-[11px] font-mono bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-1"
            title="Fit all candles in view"
          >
            <Maximize2 className="w-3 h-3" />
            Fit All
          </button>
        </div>
      </div>

      {/* Window, Session Breakdown & Warmup vs Indicator Readiness Diagnostic Strip */}
      <div className="px-4 py-1.5 bg-slate-900/95 border-b border-slate-800/80 flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono text-slate-400">
        <div className="flex flex-wrap items-center gap-3">
          <span>
            Requested:{' '}
            <strong className="text-slate-200">
              {formatCompactWindowIso(bundle.requested_window?.start || manifest?.requested_start || manifest?.start_time, tzMode)}
            </strong>
            {' → '}
            <strong className="text-slate-200">
              {formatCompactWindowIso(bundle.requested_window?.end || manifest?.requested_end || manifest?.end_time, tzMode)}
            </strong>
          </span>
          <span>
            Actual:{' '}
            <strong className="text-emerald-300">
              {formatChartTime(candles[0].time, tzMode)}
            </strong>
            {' → '}
            <strong className="text-emerald-300">
              {formatChartTime(candles[candles.length - 1].time, tzMode)}
            </strong>
            {' '}
            ({candles.length}
            {bundle.actual_window?.manifest_total_bars && bundle.actual_window.manifest_total_bars !== candles.length
              ? `/${bundle.actual_window.manifest_total_bars} manifest`
              : ''} bars)
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {!isCryptoSymbol && (
            <span>
              Sessions: <strong className="text-slate-200">RTH {rthCount}</strong>
              {extCount > 0 && <span className="text-amber-300"> • Ext {extCount}</span>}
            </span>
          )}
          <span>
            Exec Warmup: <strong className="text-slate-200">{bundle.warmup_bars_count} bars</strong>
            {readiness?.ma_slow_ready_bar && !bundle.config?.strategy_id?.includes('RSI') && (
              <span className="text-sky-300">
                {' '}• MA({params.fast_period})@{readiness.ma_fast_ready_bar} / MA({params.slow_period})@{readiness.ma_slow_ready_bar}
              </span>
            )}
            {readiness?.rsi_ready_bar && bundle.config?.strategy_id?.includes('RSI') && (
              <span className="text-purple-300"> • RSI({params.rsi_period})@{readiness.rsi_ready_bar}</span>
            )}
          </span>
        </div>
      </div>

      {/* Data Quality Warnings (explicit, non-destructive) */}
      {bundle.data_quality_warnings && bundle.data_quality_warnings.length > 0 && (
        <div className="px-4 py-1 bg-amber-950/40 border-b border-amber-800/50 text-[10px] font-mono text-amber-200 flex flex-wrap items-center gap-2">
          <AlertTriangle className="w-3 h-3 text-amber-400 flex-shrink-0" />
          <span>{bundle.data_quality_warnings.join(' • ')}</span>
        </div>
      )}

      {/* Fixed-Height Zero-Reflow OHLCV + Indicator HUD Strip */}
      <div className="px-4 h-[52px] min-h-[52px] max-h-[52px] bg-slate-950/60 border-b border-slate-800/80 flex flex-col justify-center gap-0.5 text-[11px] font-mono tabular-nums overflow-hidden">
        {hudSnapshot ? (
          <>
            <div className="flex items-center justify-between gap-2 h-[20px] whitespace-nowrap overflow-hidden">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-slate-300 font-semibold">{formatChartTime(hudSnapshot.time, tzMode)}</span>
                <span className={`px-1.5 rounded text-[10px] font-bold ${
                  (hudSnapshot.session === 'RTH' || hudSnapshot.session === 'CRYPTO_24_7')
                    ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-800/60'
                    : 'bg-amber-950/80 text-amber-300 border border-amber-800/60'
                }`}>
                  {hudSnapshot.session || (isCryptoSymbol ? 'CRYPTO_24_7' : 'RTH')}
                </span>
                <span className={`px-1.5 rounded text-[10px] font-bold ${
                  hudSnapshot.is_warmup
                    ? 'bg-slate-800 text-amber-300 border border-amber-700/50'
                    : 'bg-slate-900 text-slate-400 border border-slate-800'
                }`}>
                  {hudSnapshot.is_warmup ? 'WARMUP (NO TRADE)' : 'TRADABLE'}
                </span>
              </div>
              <div className="text-[10px] text-slate-400 flex-shrink-0">
                Candles: <strong className="text-white">{candles.length}</strong> (Warmup: {bundle.warmup_bars_count})
              </div>
            </div>
            <div className="flex items-center gap-3 h-[20px] whitespace-nowrap overflow-hidden text-[11px]">
              <span>O <strong className="text-white">{hudSnapshot.open.toFixed(priceFormat.precision)}</strong></span>
              <span>H <strong className="text-white">{hudSnapshot.high.toFixed(priceFormat.precision)}</strong></span>
              <span>L <strong className="text-white">{hudSnapshot.low.toFixed(priceFormat.precision)}</strong></span>
              <span>C <strong className={hudSnapshot.close >= hudSnapshot.open ? 'text-emerald-400' : 'text-rose-400'}>{hudSnapshot.close.toFixed(priceFormat.precision)}</strong></span>
              <span>V <strong className="text-slate-300">{hudSnapshot.volume.toLocaleString()}</strong></span>
              <span className="text-sky-400">
                MA({params.fast_period}): {hudSnapshot.maFast !== null ? hudSnapshot.maFast.toFixed(priceFormat.precision) : 'Insuff'}
              </span>
              <span className="text-amber-400">
                MA({params.slow_period}): {hudSnapshot.maSlow !== null ? hudSnapshot.maSlow.toFixed(priceFormat.precision) : 'Insuff'}
              </span>
              <span className="text-purple-400">
                RSI({params.rsi_period}): {hudSnapshot.rsi !== null ? hudSnapshot.rsi.toFixed(2) : 'Insuff'}
              </span>
            </div>
          </>
        ) : (
          <div className="flex items-center justify-between text-slate-500 whitespace-nowrap">
            <span>Hover or click any candle to inspect OHLCV, indicators, and execution fills</span>
            <span className="text-[10px] text-slate-400">Candles: <strong className="text-white">{candles.length}</strong> (Warmup: {bundle.warmup_bars_count})</span>
          </div>
        )}
      </div>

      {/* Chart Canvas Area */}
      <div className="relative w-full h-[540px] bg-[#070b14]">
        <div ref={containerRef} className="w-full h-full" />

        {/* Execution & Signal Inspection Tooltip Card: pointer-events-none during hover so canvas crosshair never flickers */}
        {activeInspection && (activeInspection.fills.length > 0 || activeInspection.signals.length > 0) && (
          <div className={`absolute top-3 left-3 z-20 max-w-md bg-slate-950/95 border border-slate-700/90 rounded-xl p-3 shadow-2xl text-[11px] font-mono backdrop-blur-sm max-h-[460px] overflow-y-auto ${
            pinnedEpoch !== null ? 'pointer-events-auto' : 'pointer-events-none select-none'
          }`}>
            <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-2">
              <div className="flex items-center gap-1.5 text-slate-200 font-bold">
                <Info className="w-3.5 h-3.5 text-indigo-400" />
                <span>Bar Inspection • {formatChartTime(activeInspection.time, tzMode)}</span>
              </div>
              {pinnedEpoch !== null && !hovered && (
                <button
                  type="button"
                  onClick={() => setPinnedEpoch(null)}
                  className="text-slate-400 hover:text-white p-0.5"
                  title="Close pinned tooltip"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Simulated Fills at this timestamp */}
            {activeInspection.fills.length > 0 && (
              <div className="space-y-2">
                <div className="text-[10px] uppercase tracking-wider text-emerald-400 font-bold">
                  Simulated Execution Fills ({activeInspection.fills.length})
                </div>
                {activeInspection.fills.map((fill) => {
                  const isBuy = fill.side.toUpperCase() === 'BUY'
                  const linkedTrade = barLookup.tradeByFillId.get(fill.simulated_fill_id)
                  return (
                    <div
                      key={fill.simulated_fill_id}
                      onClick={() => onSelectFill(fill)}
                      className={`p-2 rounded-lg border cursor-pointer transition ${
                        selectedFillId === fill.simulated_fill_id
                          ? 'bg-indigo-950/70 border-yellow-400/70'
                          : 'bg-slate-900/90 border-slate-800 hover:border-slate-600'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className={`font-bold flex items-center gap-1 ${isBuy ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {isBuy ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                          {fill.side} {fill.fill_qty} {fill.symbol} @ ${fill.fill_price.toFixed(4)}
                        </span>
                        {fill.is_partial_fill && (
                          <span className="px-1.5 py-0.2 rounded bg-amber-950 text-amber-300 border border-amber-700 text-[9px]">
                            PARTIAL
                          </span>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] text-slate-300">
                        <div>Order ID: <span className="text-white">{fill.simulated_order_id}</span></div>
                        <div>Fill ID: <span className="text-white">{fill.simulated_fill_id}</span></div>
                        <div>Time (UTC): <span className="text-slate-200">{fill.fill_time.replace('T', ' ').slice(0, 19)}</span></div>
                        <div>Fee / Slip: <span className="text-slate-200">${fill.fee.toFixed(2)} / ${fill.slippage.toFixed(4)}</span></div>
                      </div>
                      {fill.strategy_reason && (
                        <div className="mt-1 text-[10px] text-sky-300 leading-snug">
                          Reason: {fill.strategy_reason}
                        </div>
                      )}
                      {linkedTrade && linkedTrade.exit_fill_id === fill.simulated_fill_id && (
                        <div className={`mt-1 pt-1 border-t border-slate-800 flex items-center justify-between text-[10px] font-bold ${
                          linkedTrade.net_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
                        }`}>
                          <span>Closed Trade P&L (vs ${linkedTrade.entry_price.toFixed(2)}):</span>
                          <span>
                            {linkedTrade.net_pnl >= 0 ? '+' : ''}${linkedTrade.net_pnl.toFixed(2)} ({linkedTrade.return_pct.toFixed(2)}%)
                          </span>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {/* Strategy Signals firing on this bar */}
            {activeInspection.signals.length > 0 && (
              <div className="space-y-1.5 mt-2 pt-2 border-t border-slate-800">
                <div className="text-[10px] uppercase tracking-wider text-sky-400 font-bold">
                  Strategy Signals ({activeInspection.signals.length}) — Executes Next Eligible Bar
                </div>
                {activeInspection.signals.map((sig) => (
                  <div key={sig.signal_id} className="p-2 rounded-lg bg-slate-900/70 border border-slate-800 text-[10px]">
                    <div className="flex items-center justify-between">
                      <span className={sig.signal_type === 'BUY' ? 'text-sky-300 font-bold' : 'text-amber-300 font-bold'}>
                        SIG {sig.signal_type} ({sig.decision_status || 'EVALUATED'})
                      </span>
                      <span className="text-slate-400">{sig.signal_id}</span>
                    </div>
                    {sig.reason && <div className="text-slate-300 mt-0.5">{sig.reason}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Legend Footer */}
      <div className="px-4 py-2 bg-slate-950/90 border-t border-slate-800 flex flex-wrap items-center justify-between gap-2 text-[10px] text-slate-400 font-mono">
        <div className="flex flex-wrap items-center gap-4">
          <span className="flex items-center gap-1"><span className="text-emerald-400 font-bold">▲ BUY Fill</span> (Actual Execution Bar & Price)</span>
          <span className="flex items-center gap-1"><span className="text-rose-400 font-bold">▼ SELL Fill</span> (Actual Execution Bar & Price)</span>
          <span className="flex items-center gap-1"><span className="text-sky-400 font-bold">● SIG</span> (Signal Fired, Next-Bar Exec)</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-0.5 bg-sky-400 inline-block" /> MA Fast ({params.fast_period})</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-0.5 bg-amber-400 inline-block" /> MA Slow ({params.slow_period})</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-0.5 bg-purple-400 inline-block" /> RSI ({params.rsi_period})</span>
        </div>
        <div>Scroll/Drag to Zoom & Pan • Click marker or Trade row to inspect</div>
      </div>
    </div>
  )
})
