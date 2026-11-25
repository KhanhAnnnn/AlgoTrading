import React, { useState, useEffect } from 'react'
import {
  ShieldCheck,
  Send,
  AlertOctagon,
  RefreshCw,
  KeyRound,
  CheckCircle2
} from 'lucide-react'

interface ReliabilityLogsPanelProps {
  apiBase?: string
}

export const ReliabilityLogsPanel: React.FC<ReliabilityLogsPanelProps> = ({
  apiBase = 'http://127.0.0.1:8005'
}) => {
  const [data, setData] = useState<any | null>(null)
  const [refreshing, setRefreshing] = useState<boolean>(false)
  const [filterType, setFilterType] = useState<'all' | 'production' | 'test'>('all')

  const fetchReliabilityData = async () => {
    try {
      const res = await fetch(`${apiBase}/api/reliability/events`)
      if (res.ok) {
        const json = await res.json()
        setData(json)
      }
    } catch (err) {
      console.error('Error fetching reliability telemetry:', err)
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchReliabilityData()
    const timer = setInterval(fetchReliabilityData, 8000)
    return () => clearInterval(timer)
  }, [apiBase])

  const handleRefresh = () => {
    setRefreshing(true)
    fetchReliabilityData()
  }

  const recovery = data?.recovery
  const outbox = data?.outbox || data?.slack_outbox
  const outboxSummary = outbox?.summary
  const rawEvents: any[] = outbox?.events || outbox?.recent_messages || []
  const dlq = data?.dead_letter_queue
  const dlqRecords: any[] = dlq?.records || []
  const dedup = data?.deduplication

  // Filter outbox events by type
  const filteredEvents = rawEvents.filter((evt) => {
    if (filterType === 'production') return !evt.is_test_fixture
    if (filterType === 'test') return evt.is_test_fixture
    return true
  })

  return (
    <div className="flex flex-col gap-4 text-slate-200">
      {/* Header Security & Privacy Guarantee */}
      <div className="p-3 bg-slate-900 border border-slate-800 rounded-lg flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
          <div className="text-xs">
            <span className="font-semibold text-emerald-400 uppercase tracking-wider">
              Fault Tolerance & Zero Credential Disclosure:
            </span>
            <span className="text-slate-300 ml-1">
              All auth tokens, bot secrets, and account keys are strictly sanitized and never exposed over telemetry endpoints.
            </span>
          </div>
        </div>

        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-xs font-mono text-slate-300 transition-colors shrink-0"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          <span>Refresh Logs</span>
        </button>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono">
        {/* Recovery Events */}
        <div className="bg-slate-900 border border-slate-800 p-3.5 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Self-Healing Actions</span>
          <div className="text-xl font-bold text-emerald-400 mt-1">
            {recovery?.total_actions || 0}
          </div>
          <span className="text-[10px] text-slate-500">Status: {recovery?.status || 'IDLE'}</span>
        </div>

        {/* Slack Outbox Delivered */}
        <div className="bg-slate-900 border border-slate-800 p-3.5 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Slack Delivered</span>
          <div className="text-xl font-bold text-cyan-400 mt-1">
            {outboxSummary?.delivered || 0}
          </div>
          <span className="text-[10px] text-slate-500">
            Active Pending: <strong className="text-amber-400">{outboxSummary?.pending || 0}</strong>
          </span>
        </div>

        {/* Dead Letter Queue */}
        <div className="bg-slate-900 border border-slate-800 p-3.5 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Dead-Letter Queue</span>
          <div className={`text-xl font-bold mt-1 ${(dlq?.count || 0) > 0 ? 'text-amber-400' : 'text-slate-400'}`}>
            {dlq?.count || 0}
          </div>
          <span className="text-[10px] text-slate-500">Poison messages isolated</span>
        </div>

        {/* Deduplication Cache */}
        <div className="bg-slate-900 border border-slate-800 p-3.5 rounded-lg flex flex-col justify-between">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Active Dedup Keys</span>
          <div className="text-xl font-bold text-purple-400 mt-1">
            {dedup?.total_keys || 0}
          </div>
          <span className="text-[10px] text-slate-500">Idempotency store</span>
        </div>
      </div>

      {/* Self-Healing Recovery Events Log */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
              Self-Healing & Auto-Recovery Actions
            </h4>
          </div>
          <span className="text-xs font-mono text-slate-400">Total: {recovery?.total_actions || 0}</span>
        </div>

        {(!recovery?.actions_taken || recovery.actions_taken.length === 0) ? (
          <div className="py-6 text-center text-slate-500 text-xs italic">
            Zero recovery faults detected; system running cleanly without stale locks.
          </div>
        ) : (
          <div className="flex flex-col gap-1.5 font-mono text-xs">
            {recovery.actions_taken.map((action: string, i: number) => (
              <div key={i} className="flex items-center gap-2 p-2 bg-slate-950/80 rounded border border-slate-800/80 text-emerald-300">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span>{action}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Slack Notification Outbox Stream */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-2">
            <Send className="w-4 h-4 text-cyan-400" />
            <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
              Slack Notification Outbox Queue
            </h4>
          </div>

          <div className="flex items-center gap-3 font-mono text-xs text-slate-400">
            {/* Filter Buttons */}
            <div className="flex items-center gap-1 bg-slate-950 p-0.5 rounded border border-slate-800 text-[10px]">
              {(['all', 'production', 'test'] as const).map((filter) => (
                <button
                  key={filter}
                  onClick={() => setFilterType(filter)}
                  className={`px-2 py-0.5 rounded transition-colors uppercase ${filterType === filter ? 'bg-cyan-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
                >
                  {filter}
                </button>
              ))}
            </div>

            <div className="hidden md:flex items-center gap-2">
              <span>Pending: <strong className="text-amber-400">{outboxSummary?.pending || 0}</strong></span>
              <span>•</span>
              <span>Delivered: <strong className="text-emerald-400">{outboxSummary?.delivered || 0}</strong></span>
            </div>
          </div>
        </div>

        {filteredEvents.length === 0 ? (
          <div className="py-6 text-center text-slate-500 text-xs italic">
            No notification records matching the selected filter ({filterType}).
          </div>
        ) : (
          <div className="overflow-x-auto max-h-56 overflow-y-auto">
            <table className="w-full text-xs font-mono text-left">
              <thead className="sticky top-0 bg-slate-900 border-b border-slate-800 text-slate-400">
                <tr>
                  <th className="pb-2">Signal ID</th>
                  <th className="pb-2">Dedup Key</th>
                  <th className="pb-2">Type</th>
                  <th className="pb-2">Final Status</th>
                  <th className="pb-2 text-right">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredEvents.map((m, idx) => {
                  const status = m.current_status || m.status
                  const isDelivered = status === 'DELIVERED'
                  const isPending = status === 'PENDING'
                  return (
                    <tr key={`${m.signal_id}-${idx}`} className="hover:bg-slate-800/30">
                      <td className="py-2 text-slate-300 font-semibold">{m.signal_id}</td>
                      <td className="py-2 text-slate-400 text-[11px] truncate max-w-xs">{m.dedup_key}</td>
                      <td className="py-2">
                        {m.is_test_fixture ? (
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-950 text-amber-400 border border-amber-800 font-bold uppercase">
                            Test Fixture
                          </span>
                        ) : (
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800 font-bold uppercase">
                            Production
                          </span>
                        )}
                      </td>
                      <td className="py-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          isDelivered
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : isPending
                            ? 'bg-amber-950 text-amber-400 border border-amber-800'
                            : 'bg-rose-950 text-rose-400 border border-rose-800'
                        }`}>
                          {status} {m.attempt_count > 1 ? `(${m.attempt_count} attempts)` : ''}
                        </span>
                      </td>
                      <td className="py-2 text-right text-slate-400">{m.latest_iso_time || m.iso_time || 'N/A'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Dead-Letter Queue (DLQ) Inspector */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <AlertOctagon className="w-4 h-4 text-rose-400" />
            <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
              Dead-Letter Queue (DLQ) Failure Inspector
            </h4>
          </div>
          <span className="text-xs font-mono text-slate-400">Total Failed: {dlqRecords.length}</span>
        </div>

        {dlqRecords.length === 0 ? (
          <div className="py-6 text-center text-slate-500 text-xs italic">
            Zero messages quarantined in Dead-Letter Queue. All outgoing dispatches succeeded.
          </div>
        ) : (
          <div className="overflow-x-auto max-h-52 overflow-y-auto">
            <table className="w-full text-xs font-mono text-left">
              <thead className="sticky top-0 bg-slate-900 border-b border-slate-800 text-slate-400">
                <tr>
                  <th className="pb-2">Time</th>
                  <th className="pb-2">Signal ID</th>
                  <th className="pb-2">Type</th>
                  <th className="pb-2">Failure Error Reason</th>
                  <th className="pb-2 text-center">Retriable</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {dlqRecords.map((item, idx) => (
                  <tr key={`${item.signal_id}-${idx}`} className="hover:bg-slate-800/30">
                    <td className="py-2 text-slate-400 whitespace-nowrap">{item.iso_time || 'N/A'}</td>
                    <td className="py-2 font-bold text-slate-200">{item.signal_id}</td>
                    <td className="py-2">
                      {item.is_test_fixture ? (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-950 text-amber-400 border border-amber-800 font-bold uppercase">
                          Test Fixture
                        </span>
                      ) : (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-rose-950 text-rose-400 border border-rose-800 font-bold uppercase">
                          Production
                        </span>
                      )}
                    </td>
                    <td className="py-2 text-rose-300 max-w-sm truncate" title={item.error}>{item.error}</td>
                    <td className="py-2 text-center">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${item.retriable ? 'bg-amber-950 text-amber-400 border border-amber-800' : 'bg-slate-800 text-slate-400'}`}>
                        {item.retriable ? 'YES' : 'NO'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Deduplication Storage Index */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-purple-400" />
            <h4 className="font-semibold text-xs text-slate-200 uppercase tracking-wider">
              Signal Deduplication Hash Keys Store
            </h4>
          </div>
          <span className="text-xs font-mono text-slate-400">Total Keys: {dedup?.total_keys || 0}</span>
        </div>

        {(!dedup?.keys || dedup.keys.length === 0) ? (
          <div className="py-6 text-center text-slate-500 text-xs italic">
            No deduplication keys registered.
          </div>
        ) : (
          <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto p-1 font-mono text-[11px]">
            {dedup.keys.map((k: string, i: number) => (
              <span key={i} className="px-2 py-0.5 bg-slate-950 border border-slate-800 text-slate-300 rounded">
                {k}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
