import React from 'react'
import type { PipelineStatus } from '../types'
import { Server, Activity, Database, Clock, Users, Cpu, Coins } from 'lucide-react'

interface PipelineMonitorPanelProps {
  status: PipelineStatus | null
}

export const PipelineMonitorPanel: React.FC<PipelineMonitorPanelProps> = ({ status }) => {
  const priceProducer = status?.producer_status?.price_producer
  const newsProducer = status?.producer_status?.news_producer
  const cryptoProducer = status?.producer_status?.crypto_producer
  const cryptoHandler = status?.producer_status?.crypto_handler

  const formatUptime = (sec?: number) => {
    if (!sec || sec < 0) return '0s'
    const m = Math.floor(sec / 60)
    const s = sec % 60
    if (m === 0) return `${s}s`
    const h = Math.floor(m / 60)
    const remM = m % 60
    if (h === 0) return `${m}m ${s}s`
    return `${h}h ${remM}m`
  }

  return (
    <div className="flex flex-col h-full bg-slate-950 rounded-xl border border-slate-800 overflow-hidden shadow-xl">
      {/* Panel Header */}
      <div className="p-3 bg-slate-900/80 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Server className="w-4 h-4 text-cyan-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            Pipeline Health & Stream Engines
          </h2>
        </div>

        <div className="flex items-center gap-1.5 text-[11px] font-mono text-slate-400">
          <Users className="w-3.5 h-3.5 text-blue-400" />
          <span>{status?.active_ws_clients || 1} WS Client(s)</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3 font-mono text-xs">
        {/* Continuous Producers Status */}
        <div className="p-2.5 bg-slate-900/40 rounded-lg border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-300 flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-emerald-400" />
              Continuous Producers & Handlers
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {/* Price Producer */}
            <div className="bg-slate-950 p-2 rounded border border-slate-800/80 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${priceProducer?.active ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                  <span className="font-semibold text-slate-200 text-[11px]">Stocks Price (1m)</span>
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  Uptime: {formatUptime(priceProducer?.uptime_sec)}
                </p>
              </div>
              <span className="text-[10px] px-1.5 py-0.5 rounded font-bold bg-slate-800 text-slate-300 border border-slate-700">
                {priceProducer?.status || 'RUNNING'}
              </span>
            </div>

            {/* News Producer */}
            <div className="bg-slate-950 p-2 rounded border border-slate-800/80 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${newsProducer?.active ? 'bg-purple-400' : 'bg-slate-500'}`} />
                  <span className="font-semibold text-slate-200 text-[11px]">Stocks News (VADER)</span>
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  Uptime: {formatUptime(newsProducer?.uptime_sec)}
                </p>
              </div>
              <span className="text-[10px] px-1.5 py-0.5 rounded font-bold bg-slate-800 text-slate-300 border border-slate-700">
                {newsProducer?.status || 'RUNNING'}
              </span>
            </div>

            {/* Crypto Producer */}
            <div className="bg-slate-950 p-2 rounded border border-slate-800/80 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${cryptoProducer?.active ? 'bg-amber-400' : 'bg-amber-500'}`} />
                  <span className="font-semibold text-slate-200 text-[11px]">Crypto Stream (24/7)</span>
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  Uptime: {formatUptime(cryptoProducer?.uptime_sec)}
                </p>
              </div>
              <span className="text-[10px] px-1.5 py-0.5 rounded font-bold bg-amber-950 text-amber-300 border border-amber-800">
                {cryptoProducer?.status || 'STREAMING'}
              </span>
            </div>

            {/* Crypto Handler */}
            <div className="bg-slate-950 p-2 rounded border border-slate-800/80 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-cyan-400" />
                  <span className="font-semibold text-slate-200 text-[11px]">Crypto Handler (DRY)</span>
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  Guard: DRY_RUN
                </p>
              </div>
              <span className="text-[10px] px-1.5 py-0.5 rounded font-bold bg-cyan-950 text-cyan-300 border border-cyan-800">
                {cryptoHandler?.status || 'ARMED'}
              </span>
            </div>
          </div>
        </div>

        {/* Redpanda Cluster */}
        <div className="p-2.5 bg-slate-900/40 rounded-lg border border-slate-800">
          <div className="flex items-center justify-between mb-1">
            <span className="font-bold text-slate-300 flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-red-400" />
              Redpanda Kafka Brokers
            </span>
            <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              {status?.redpanda_connected ? 'CONNECTED' : 'DISCONNECTED'}
            </span>
          </div>
          <p className="text-[11px] text-slate-500">
            Brokers: {status?.brokers?.join(', ') || 'localhost:9092, localhost:9093'}
          </p>
        </div>

        {/* Flink Streaming Jobs: Stocks & Crypto */}
        <div className="p-2.5 bg-slate-900/40 rounded-lg border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-300 flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-blue-400" />
              Apache Flink Streaming Jobs
            </span>
          </div>

          {/* Stocks Flink Job */}
          <div className="bg-slate-950 p-2 rounded border border-slate-800/80 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                <span className="font-semibold text-slate-200 text-[11px]">Stocks Signals Engine</span>
              </div>
              <p className="text-[10px] text-slate-500 truncate max-w-[200px]">
                ID: {status?.flink_job_id || 'c0955d4aa73c9c2197c936f89ba07f22'}
              </p>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded font-bold bg-blue-950 text-blue-300 border border-blue-800">
              {status?.flink_status || 'RUNNING'}
            </span>
          </div>

          {/* Crypto Flink Job */}
          <div className="bg-slate-950 p-2 rounded border border-slate-800/80 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                <span className="font-semibold text-slate-200 text-[11px]">Crypto Signals Engine</span>
              </div>
              <p className="text-[10px] text-slate-500 truncate max-w-[200px]">
                ID: {status?.crypto_flink_job_id || 'd2b415147232c6cd528b129dfc359c71'}
              </p>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded font-bold bg-amber-950 text-amber-300 border border-amber-800">
              {status?.crypto_flink_status || 'RUNNING'}
            </span>
          </div>
        </div>

        {/* Kafka Topics Ingested */}
        <div className="p-2.5 bg-slate-900/40 rounded-lg border border-slate-800">
          <span className="font-bold text-slate-300 block mb-2">Kafka Topics Ingested</span>

          {/* Stocks Topics */}
          <span className="text-[10px] text-slate-400 block mb-1 font-semibold uppercase">Stocks Topics</span>
          <div className="grid grid-cols-3 gap-1.5 text-center mb-2">
            <div className="bg-slate-950 p-1.5 rounded border border-slate-800/80">
              <span className="text-[9px] text-slate-500 block truncate">stock-prices</span>
              <span className="text-xs font-bold text-blue-400">
                {status?.topics?.stock_prices?.toLocaleString() ?? 0}
              </span>
            </div>
            <div className="bg-slate-950 p-1.5 rounded border border-slate-800/80">
              <span className="text-[9px] text-slate-500 block truncate">market-news</span>
              <span className="text-xs font-bold text-purple-400">
                {status?.topics?.market_news?.toLocaleString() ?? 0}
              </span>
            </div>
            <div className="bg-slate-950 p-1.5 rounded border border-slate-800/80">
              <span className="text-[9px] text-slate-500 block truncate">trading-signals</span>
              <span className="text-xs font-bold text-amber-400">
                {status?.topics?.trading_signals?.toLocaleString() ?? 0}
              </span>
            </div>
          </div>

          {/* Crypto Topics */}
          <span className="text-[10px] text-amber-400/90 block mb-1 font-semibold uppercase flex items-center gap-1">
            <Coins className="w-3 h-3 text-amber-400" />
            Crypto 24/7 Topics
          </span>
          <div className="grid grid-cols-4 gap-1.5 text-center">
            <div className="bg-slate-950 p-1.5 rounded border border-slate-800/80">
              <span className="text-[9px] text-slate-500 block truncate">crypto-bars-1m</span>
              <span className="text-xs font-bold text-amber-400">
                {status?.topics?.crypto_bars_1m?.toLocaleString() ?? 0}
              </span>
            </div>
            <div className="bg-slate-950 p-1.5 rounded border border-slate-800/80">
              <span className="text-[9px] text-slate-500 block truncate">crypto-trades</span>
              <span className="text-xs font-bold text-amber-300">
                {status?.topics?.crypto_trades?.toLocaleString() ?? 0}
              </span>
            </div>
            <div className="bg-slate-950 p-1.5 rounded border border-slate-800/80">
              <span className="text-[9px] text-slate-500 block truncate">crypto-news</span>
              <span className="text-xs font-bold text-purple-400">
                {status?.topics?.crypto_news?.toLocaleString() ?? 0}
              </span>
            </div>
            <div className="bg-slate-950 p-1.5 rounded border border-slate-800/80">
              <span className="text-[9px] text-slate-500 block truncate">crypto-signals</span>
              <span className="text-xs font-bold text-emerald-400">
                {status?.topics?.crypto_signals?.toLocaleString() ?? 0}
              </span>
            </div>
          </div>
        </div>

        {/* Timestamps & Data Latency */}
        <div className="p-2.5 bg-slate-900/40 rounded-lg border border-slate-800">
          <span className="font-bold text-slate-300 block mb-1 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            Timestamps & Latency
          </span>
          <div className="space-y-1.5 text-[11px] text-slate-400 mt-2">
            <div className="flex justify-between">
              <span className="text-slate-500">Last Stock Candle:</span>
              <span className="text-slate-200">
                {status?.last_candle_timestamp
                  ? new Date(status.last_candle_timestamp).toUTCString().slice(5, 22) + ' UTC'
                  : 'N/A'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Last Crypto Candle:</span>
              <span className="text-amber-300">
                {status?.last_crypto_candle_timestamp
                  ? new Date(status.last_crypto_candle_timestamp).toUTCString().slice(5, 22) + ' UTC'
                  : 'Active'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Stocks Latency:</span>
              <span className="text-cyan-400 font-bold">
                {status?.latency_label || 'Market Closed'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Crypto Latency:</span>
              <span className="text-amber-400 font-bold">
                {status?.crypto_latency_label || '24/7 Live'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
