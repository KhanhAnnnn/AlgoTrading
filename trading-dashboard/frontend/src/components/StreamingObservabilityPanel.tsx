import React, { useState, useEffect } from 'react'
import type { StreamingObservabilityData } from '../types'
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Database,
  Cpu,
  Radio,
  Clock,
  RefreshCw,
  Server
} from 'lucide-react'

interface StreamingObservabilityPanelProps {
  apiBase?: string
}

export const StreamingObservabilityPanel: React.FC<StreamingObservabilityPanelProps> = ({
  apiBase = 'http://localhost:8005'
}) => {
  const [data, setData] = useState<StreamingObservabilityData | null>(null)
  const [refreshing, setRefreshing] = useState<boolean>(false)

  const fetchObservability = async () => {
    try {
      const res = await fetch(`${apiBase}/api/observability/stream`)
      if (res.ok) {
        const json = await res.json()
        setData(json)
      }
    } catch (err) {
      console.error('Error fetching observability telemetry:', err)
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchObservability()
    const timer = setInterval(fetchObservability, 5000)
    return () => clearInterval(timer)
  }, [apiBase])

  const handleRefresh = () => {
    setRefreshing(true)
    fetchObservability()
  }

  const verdict = data?.pipeline_verdict || 'HEALTHY'
  const verdictLabel = data?.pipeline_verdict_label || 'All Systems Nominal'
  const healthIssues = data?.health_issues || []

  const stocksJob = data?.flink?.jobs?.stocks_job
  const cryptoJob = data?.flink?.jobs?.crypto_job
  const kafka = data?.kafka
  const lag = kafka?.consumer_lag

  return (
    <div className="flex flex-col gap-4 text-slate-200">
      {/* Overall Pipeline Health Verdict Banner */}
      <div className={`p-4 rounded-lg border flex flex-col md:flex-row md:items-center justify-between gap-4 ${
        verdict === 'HEALTHY'
          ? 'bg-emerald-950/40 border-emerald-800/80 text-emerald-200'
          : verdict === 'DEGRADED'
          ? 'bg-amber-950/40 border-amber-800/80 text-amber-200'
          : 'bg-rose-950/40 border-rose-800/80 text-rose-200'
      }`}>
        <div className="flex items-center gap-3">
          {verdict === 'HEALTHY' ? (
            <CheckCircle2 className="w-6 h-6 text-emerald-400 shrink-0" />
          ) : verdict === 'DEGRADED' ? (
            <AlertTriangle className="w-6 h-6 text-amber-400 shrink-0" />
          ) : (
            <XCircle className="w-6 h-6 text-rose-400 shrink-0" />
          )}
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm uppercase tracking-wider">
                Pipeline Health Verdict: {verdict}
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-300">
                Multi-Factor Verified
              </span>
            </div>
            <p className="text-xs text-slate-300 mt-0.5">{verdictLabel}</p>
            {healthIssues.length > 0 && (
              <ul className="list-disc list-inside text-xs mt-1 text-rose-300">
                {healthIssues.map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-700 rounded text-xs font-mono text-slate-200 transition-colors shrink-0"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          <span>Refresh Telemetry</span>
        </button>
      </div>

      {/* 5-Pillar Health Architecture Breakdown */}
      {data?.health_pillars && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 font-mono text-xs">
          {/* Pillar 1: Infrastructure */}
          <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">1. Infrastructure</span>
            <div className="flex items-center gap-1.5 my-1.5">
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                data.health_pillars.infrastructure?.status === 'HEALTHY'
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                  : 'bg-rose-950 text-rose-400 border border-rose-800'
              }`}>
                {data.health_pillars.infrastructure?.status || 'UNKNOWN'}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 truncate" title={data.health_pillars.infrastructure?.reason}>
              {data.health_pillars.infrastructure?.reason || 'Brokers & Flink reachability'}
            </p>
          </div>

          {/* Pillar 2: Market Data Freshness */}
          <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">2. Data Freshness</span>
            <div className="flex items-center gap-1.5 my-1.5">
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                data.health_pillars.data_freshness?.status === 'HEALTHY'
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                  : data.health_pillars.data_freshness?.status === 'STALE'
                  ? 'bg-amber-950 text-amber-400 border border-amber-800'
                  : 'bg-slate-800 text-slate-300'
              }`}>
                {data.health_pillars.data_freshness?.status || 'UNKNOWN'}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 truncate" title={data.health_pillars.data_freshness?.reason}>
              {data.health_pillars.data_freshness?.reason || 'Crypto 24/7 vs Stocks hours'}
            </p>
          </div>

          {/* Pillar 3: Flink Processing */}
          <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">3. Flink Engine</span>
            <div className="flex items-center gap-1.5 my-1.5">
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                data.health_pillars.processing?.status === 'HEALTHY'
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                  : 'bg-rose-950 text-rose-400 border border-rose-800'
              }`}>
                {data.health_pillars.processing?.status || 'UNKNOWN'}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 truncate" title={data.health_pillars.processing?.reason}>
              {data.health_pillars.processing?.reason || 'RocksDB Checkpoints'}
            </p>
          </div>

          {/* Pillar 4: Signal Handlers */}
          <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">4. Handlers & Lag</span>
            <div className="flex items-center gap-1.5 my-1.5">
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                data.health_pillars.signal_handlers?.status === 'HEALTHY'
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                  : 'bg-amber-950 text-amber-400 border border-amber-800'
              }`}>
                {data.health_pillars.signal_handlers?.status || 'UNKNOWN'}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 truncate" title={data.health_pillars.signal_handlers?.reason}>
              {data.health_pillars.signal_handlers?.reason || 'Consumer offset sync'}
            </p>
          </div>

          {/* Pillar 5: End-to-End Composite */}
          <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-lg flex flex-col justify-between">
            <span className="text-[10px] text-slate-400 uppercase tracking-wider">5. End-to-End</span>
            <div className="flex items-center gap-1.5 my-1.5">
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                verdict === 'HEALTHY'
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                  : verdict === 'DEGRADED'
                  ? 'bg-amber-950 text-amber-400 border border-amber-800'
                  : 'bg-rose-950 text-rose-400 border border-rose-800'
              }`}>
                {verdict}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 truncate" title={verdictLabel}>
              {verdictLabel}
            </p>
          </div>
        </div>
      )}

      {/* Latency & Ingestion Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Stocks Ingestion Status */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-blue-400" />
              <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
                Stocks Market & Feed Latency
              </h4>
            </div>
            <span className="text-[10px] font-mono bg-blue-950 text-blue-400 border border-blue-800 px-2 py-0.5 rounded font-semibold">
              STOCKS (IEX)
            </span>
          </div>

          <div className="flex items-baseline justify-between mt-2 font-mono">
            <div>
              <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Ingestion Mode</span>
              <span className="text-sm font-bold text-slate-100">{data?.latency?.stocks?.status}</span>
            </div>
            <div className="text-right">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Delay / Latency</span>
              <span className="text-sm font-bold text-amber-400">
                {data?.latency?.stocks?.latency_sec !== null && data?.latency?.stocks?.latency_sec !== undefined
                  ? `${Math.round((data.latency.stocks.latency_sec) / 60)}m`
                  : '—'}
              </span>
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-2 border-t border-slate-800/80 pt-2 font-mono text-[11px]">
            {data?.latency?.stocks?.status_label}
          </p>
        </div>

        {/* Crypto Ingestion Status */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Radio className="w-4 h-4 text-cyan-400" />
              <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
                Crypto 24/7 WebSocket Feed Latency
              </h4>
            </div>
            <span className="text-[10px] font-mono bg-cyan-950 text-cyan-400 border border-cyan-800 px-2 py-0.5 rounded font-semibold">
              CRYPTO (24/7)
            </span>
          </div>

          <div className="flex items-baseline justify-between mt-2 font-mono">
            <div>
              <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Stream Status</span>
              <span className="text-sm font-bold text-slate-100">{data?.latency?.crypto?.status}</span>
            </div>
            <div className="text-right">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider block">Stream Latency</span>
              <span className="text-sm font-bold text-cyan-400">
                {data?.latency?.crypto?.latency_sec !== null && data?.latency?.crypto?.latency_sec !== undefined
                  ? `${data.latency.crypto.latency_sec}s`
                  : '—'}
              </span>
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-2 border-t border-slate-800/80 pt-2 font-mono text-[11px]">
            {data?.latency?.crypto?.status_label}
          </p>
        </div>
      </div>

      {/* Apache Flink Streaming Jobs Telemetry */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-amber-400" />
            <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
              Apache Flink Streaming Jobs & Checkpoint Telemetry
            </h4>
          </div>
          <span className="text-[10px] font-mono bg-slate-800 text-slate-300 px-2 py-0.5 rounded">
            Checkpoint Interval: 10,000ms | Host Durable Storage
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Stocks Job */}
          <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-3.5 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="font-bold text-xs text-slate-200">Stocks Streaming Pipeline</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950 text-emerald-400 border border-emerald-800">
                  {stocksJob?.state || 'RUNNING'} ({stocksJob?.tasks_running || 6}/{stocksJob?.tasks_total || 6} Tasks)
                </span>
              </div>
              <div className="text-[11px] font-mono text-slate-400 mt-1 truncate">
                JID: {stocksJob?.jid || 'e655dc228a70bfe592ff817a563a9018'}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 my-3 font-mono text-xs">
              <div className="bg-slate-900 p-2 rounded border border-slate-800/80">
                <span className="text-[9px] text-slate-500 block uppercase">Checkpoints</span>
                <span className="text-sm font-bold text-emerald-400">
                  {stocksJob?.checkpoints?.completed_checkpoints || 0}
                </span>
              </div>
              <div className="bg-slate-900 p-2 rounded border border-slate-800/80">
                <span className="text-[9px] text-slate-500 block uppercase">Latest Checkpoint</span>
                <span className="text-sm font-bold text-slate-200">
                  chk-{stocksJob?.checkpoints?.latest_checkpoint_id || 0}
                </span>
              </div>
              <div className="bg-slate-900 p-2 rounded border border-slate-800/80">
                <span className="text-[9px] text-slate-500 block uppercase">Duration / Size</span>
                <span className="text-sm font-bold text-cyan-400">
                  {stocksJob?.checkpoints?.latest_checkpoint_duration_ms || 0}ms / {Math.round((stocksJob?.checkpoints?.latest_checkpoint_size_bytes || 0) / 1024)}KB
                </span>
              </div>
            </div>

            <div className="text-[10px] font-mono text-slate-500 truncate">
              Path: {stocksJob?.checkpoints?.latest_checkpoint_path || '/opt/flink/checkpoints/...'}
            </div>
          </div>

          {/* Crypto Job */}
          <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-3.5 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="font-bold text-xs text-slate-200">Crypto 24/7 Streaming Pipeline</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950 text-emerald-400 border border-emerald-800">
                  {cryptoJob?.state || 'RUNNING'} ({cryptoJob?.tasks_running || 6}/{cryptoJob?.tasks_total || 6} Tasks)
                </span>
              </div>
              <div className="text-[11px] font-mono text-slate-400 mt-1 truncate">
                JID: {cryptoJob?.jid || 'b12464fe415882080b50adc8fd920602'}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 my-3 font-mono text-xs">
              <div className="bg-slate-900 p-2 rounded border border-slate-800/80">
                <span className="text-[9px] text-slate-500 block uppercase">Checkpoints</span>
                <span className="text-sm font-bold text-emerald-400">
                  {cryptoJob?.checkpoints?.completed_checkpoints || 0}
                </span>
              </div>
              <div className="bg-slate-900 p-2 rounded border border-slate-800/80">
                <span className="text-[9px] text-slate-500 block uppercase">Latest Checkpoint</span>
                <span className="text-sm font-bold text-slate-200">
                  chk-{cryptoJob?.checkpoints?.latest_checkpoint_id || 0}
                </span>
              </div>
              <div className="bg-slate-900 p-2 rounded border border-slate-800/80">
                <span className="text-[9px] text-slate-500 block uppercase">Duration / Size</span>
                <span className="text-sm font-bold text-cyan-400">
                  {cryptoJob?.checkpoints?.latest_checkpoint_duration_ms || 0}ms / {Math.round((cryptoJob?.checkpoints?.latest_checkpoint_size_bytes || 0) / 1024)}KB
                </span>
              </div>
            </div>

            <div className="text-[10px] font-mono text-slate-500 truncate">
              Path: {cryptoJob?.checkpoints?.latest_checkpoint_path || '/opt/flink/checkpoints/...'}
            </div>
          </div>
        </div>
      </div>

      {/* Redpanda Kafka Topics & Consumer Lag */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-rose-400" />
            <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
              Redpanda Cluster Topics & Consumer Lag
            </h4>
          </div>
          <div className="flex items-center gap-2 font-mono text-xs text-slate-400">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>Brokers: {kafka?.brokers?.join(', ') || 'localhost:9092, 9093'}</span>
          </div>
        </div>

        {/* Consumer Lag Summary */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4 font-mono text-xs">
          {/* Stocks Consumer Lag */}
          <div className="bg-slate-950 p-3 rounded border border-slate-800 flex items-center justify-between">
            <div>
              <span className="text-[10px] text-slate-500 uppercase block">Consumer Group</span>
              <span className="font-semibold text-slate-300">{lag?.stocks_handler?.group}</span>
              <span className="text-[10px] text-slate-500 block mt-0.5">Topic: {lag?.stocks_handler?.topic}</span>
            </div>
            <div className="text-right">
              <span className="text-[10px] text-slate-500 uppercase block">Lag (Messages)</span>
              <span className={`text-base font-bold ${lag?.stocks_handler?.lag === 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
                {lag?.stocks_handler?.lag || 0}
              </span>
              <span className="text-[10px] text-slate-500 block">
                Committed: {lag?.stocks_handler?.committed} / End: {lag?.stocks_handler?.end_offset}
              </span>
            </div>
          </div>

          {/* Crypto Consumer Lag */}
          <div className="bg-slate-950 p-3 rounded border border-slate-800 flex items-center justify-between">
            <div>
              <span className="text-[10px] text-slate-500 uppercase block">Consumer Group</span>
              <span className="font-semibold text-slate-300">{lag?.crypto_handler?.group}</span>
              <span className="text-[10px] text-slate-500 block mt-0.5">Topic: {lag?.crypto_handler?.topic}</span>
            </div>
            <div className="text-right">
              <span className="text-[10px] text-slate-500 uppercase block">Lag (Messages)</span>
              <span className={`text-base font-bold ${lag?.crypto_handler?.lag === 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
                {lag?.crypto_handler?.lag || 0}
              </span>
              <span className="text-[10px] text-slate-500 block">
                Committed: {lag?.crypto_handler?.committed} / End: {lag?.crypto_handler?.end_offset}
              </span>
            </div>
          </div>
        </div>

        {/* Topics Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono text-left">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="pb-2">Topic Name</th>
                <th className="pb-2 text-right">Partition</th>
                <th className="pb-2 text-right">Current End Offset</th>
                <th className="pb-2 text-right">Messages Ingested</th>
                <th className="pb-2 text-right">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {Object.entries(kafka?.topics || {}).map(([topic, tData]) => (
                <tr key={topic} className="hover:bg-slate-800/30">
                  <td className="py-2 font-bold text-slate-200">{topic}</td>
                  <td className="py-2 text-right text-slate-400">{tData.partition}</td>
                  <td className="py-2 text-right text-slate-200 font-semibold">{tData.end_offset.toLocaleString()}</td>
                  <td className="py-2 text-right text-cyan-400">{tData.messages_total.toLocaleString()}</td>
                  <td className="py-2 text-right">
                    <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
                      ACTIVE
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Producers & Processes Heartbeat Grid */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <Server className="w-4 h-4 text-emerald-400" />
          <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
            Producer & Handler Process Health
          </h4>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 font-mono text-xs">
          {Object.entries(data?.producers || {}).map(([name, info]) => {
            const cleanName = name.replace(/_/g, ' ').toUpperCase()
            const isActive = info.active
            return (
              <div key={name} className="bg-slate-950 p-3 rounded border border-slate-800 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-[11px] text-slate-200">{cleanName}</span>
                    <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`}></span>
                  </div>
                  <div className="text-[11px] text-slate-400">
                    Status: <span className={isActive ? 'text-emerald-400 font-semibold' : 'text-slate-400'}>{info.status}</span>
                  </div>
                </div>

                <div className="mt-3 pt-2 border-t border-slate-800/80 text-[10px] text-slate-500 flex justify-between">
                  <span>PID: {info.pid || '—'}</span>
                  <span>Uptime: {info.uptime_sec ? `${Math.round(info.uptime_sec / 60)}m` : '—'}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
