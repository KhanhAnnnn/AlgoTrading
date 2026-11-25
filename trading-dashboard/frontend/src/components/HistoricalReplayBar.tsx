import React from 'react'
import { Play, Pause, RotateCcw, Clock } from 'lucide-react'

interface HistoricalReplayBarProps {
  isPlaying: boolean
  onTogglePlay: () => void
  onReset: () => void
  speed: number
  onChangeSpeed: (speed: number) => void
  currentIndex: number
  totalCount: number
  currentTimeStr: string
  onScrub: (index: number) => void
}

export const HistoricalReplayBar: React.FC<HistoricalReplayBarProps> = ({
  isPlaying,
  onTogglePlay,
  onReset,
  speed,
  onChangeSpeed,
  currentIndex,
  totalCount,
  currentTimeStr,
  onScrub,
}) => {
  const speeds = [1, 5, 10, 30]

  return (
    <div className="bg-slate-900 border-t border-purple-500/40 p-3 flex flex-wrap items-center justify-between gap-4 font-mono text-xs select-none shadow-2xl backdrop-blur sticky bottom-0 z-20">
      {/* Playback Controls */}
      <div className="flex items-center gap-2">
        <button
          onClick={onTogglePlay}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-bold transition-colors shadow-lg shadow-purple-600/30"
          title={isPlaying ? 'Pause Replay' : 'Start Replay'}
        >
          {isPlaying ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current" />}
          <span>{isPlaying ? 'PAUSE' : 'PLAY'}</span>
        </button>

        <button
          onClick={onReset}
          className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
          title="Reset to beginning"
        >
          <RotateCcw className="w-4 h-4" />
        </button>

        {/* Speed Selector */}
        <div className="flex bg-slate-950 p-0.5 rounded-lg border border-slate-800 ml-2">
          {speeds.map((s) => (
            <button
              key={s}
              onClick={() => onChangeSpeed(s)}
              className={`px-2 py-1 rounded text-[11px] font-bold transition-colors ${
                speed === s
                  ? 'bg-purple-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      {/* Scrubber Slider */}
      <div className="flex-1 min-w-[200px] flex items-center gap-3">
        <span className="text-[11px] text-slate-400 shrink-0">
          Bar {currentIndex + 1} / {totalCount}
        </span>
        <input
          type="range"
          min={0}
          max={Math.max(0, totalCount - 1)}
          value={currentIndex}
          onChange={(e) => onScrub(Number(e.target.value))}
          className="flex-1 accent-purple-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
        />
      </div>

      {/* Replay Timestamp Display */}
      <div className="flex items-center gap-2 text-purple-300 bg-purple-950/60 px-3 py-1.5 rounded-lg border border-purple-500/30">
        <Clock className="w-3.5 h-3.5 text-purple-400 shrink-0" />
        <span className="text-[11px] font-semibold">{currentTimeStr || '00:00:00'}</span>
      </div>
    </div>
  )
}
