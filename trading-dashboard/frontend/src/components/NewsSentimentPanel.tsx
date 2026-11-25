import React, { useState, useMemo } from 'react'
import type { NewsItem } from '../types'
import { Newspaper, ArrowUpRight, TrendingUp, TrendingDown, Minus, Search } from 'lucide-react'

interface NewsSentimentPanelProps {
  news: NewsItem[]
  selectedSymbol: string
}

export const NewsSentimentPanel: React.FC<NewsSentimentPanelProps> = ({
  news,
}) => {
  const [symbolFilter, setSymbolFilter] = useState<'ALL' | 'NVDA' | 'AAPL'>('ALL')
  const [sentimentFilter, setSentimentFilter] = useState<'ALL' | 'BULLISH' | 'BEARISH' | 'NEUTRAL'>('ALL')
  const [searchQuery, setSearchQuery] = useState('')

  const filteredNews = useMemo(() => {
    return news.filter((item) => {
      // Symbol match
      if (symbolFilter !== 'ALL' && item.symbol !== symbolFilter) {
        return false
      }
      // Sentiment match
      if (sentimentFilter !== 'ALL' && item.sentiment_label !== sentimentFilter) {
        return false
      }
      // Search query match
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const inHeadline = item.headline.toLowerCase().includes(q)
        const inSummary = item.summary.toLowerCase().includes(q)
        if (!inHeadline && !inSummary) return false
      }
      return true
    })
  }, [news, symbolFilter, sentimentFilter, searchQuery])

  const getSentimentBadge = (item: NewsItem) => {
    if (item.sentiment_label === 'BULLISH') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-950/70 text-emerald-400 border border-emerald-800/60 font-mono text-[11px] font-semibold">
          <TrendingUp className="w-3 h-3" />
          +{item.sentiment_score.toFixed(3)} Bullish
        </span>
      )
    }
    if (item.sentiment_label === 'BEARISH') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-950/70 text-rose-400 border border-rose-800/60 font-mono text-[11px] font-semibold">
          <TrendingDown className="w-3 h-3" />
          {item.sentiment_score.toFixed(3)} Bearish
        </span>
      )
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-mono text-[11px] font-semibold">
        <Minus className="w-3 h-3 text-slate-400" />
        {item.sentiment_score.toFixed(3)} Neutral
      </span>
    )
  }

  return (
    <div className="flex flex-col h-full bg-slate-950 rounded-xl border border-slate-800 overflow-hidden shadow-xl">
      {/* Panel Header */}
      <div className="p-3 bg-slate-900/80 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Newspaper className="w-4 h-4 text-blue-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            Market News & Sentiment
          </h2>
          <span className="px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 text-[10px] font-mono">
            {filteredNews.length} / {news.length}
          </span>
        </div>

        {/* Filter Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Quick Search */}
          <div className="relative">
            <Search className="w-3 h-3 text-slate-500 absolute left-2 top-2" />
            <input
              type="text"
              placeholder="Filter headlines..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-6 pr-2 py-0.5 bg-slate-950 border border-slate-800 rounded text-[11px] text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500 w-28 sm:w-36 font-mono"
            />
          </div>

          {/* Symbol Quick Filter */}
          <div className="flex bg-slate-950 p-0.5 rounded border border-slate-800 text-[11px]">
            {(['ALL', 'NVDA', 'AAPL'] as const).map((sym) => (
              <button
                key={sym}
                onClick={() => setSymbolFilter(sym)}
                className={`px-2 py-0.5 rounded font-semibold transition-colors ${
                  symbolFilter === sym
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>

          {/* Sentiment Filter */}
          <div className="flex bg-slate-950 p-0.5 rounded border border-slate-800 text-[11px]">
            {(['ALL', 'BULLISH', 'BEARISH', 'NEUTRAL'] as const).map((sent) => (
              <button
                key={sent}
                onClick={() => setSentimentFilter(sent)}
                className={`px-2 py-0.5 rounded font-semibold transition-colors ${
                  sentimentFilter === sent
                    ? 'bg-slate-700 text-slate-100'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {sent}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* News Feed List */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60 p-2 space-y-2">
        {filteredNews.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-xs italic">
            No news articles found matching the current filters.
          </div>
        ) : (
          filteredNews.map((item, idx) => (
            <div
              key={`${item.id}-${idx}`}
              className="p-3 bg-slate-900/30 hover:bg-slate-900/70 rounded-lg transition-colors border border-slate-800/40"
            >
              <div className="flex items-start justify-between gap-3 mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="px-1.5 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800 text-[10px] font-bold font-mono">
                    {item.symbol}
                  </span>
                  <span className="text-[11px] text-slate-400 font-mono">
                    {new Date(item.created_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </span>
                </div>
                {getSentimentBadge(item)}
              </div>

              <h3 className="text-xs font-semibold text-slate-200 hover:text-blue-400 transition-colors leading-snug mb-1">
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 group"
                  >
                    <span>{item.headline}</span>
                    <ArrowUpRight className="w-3 h-3 text-slate-500 group-hover:text-blue-400 shrink-0" />
                  </a>
                ) : (
                  item.headline
                )}
              </h3>

              {item.summary && (
                <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                  {item.summary}
                </p>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
