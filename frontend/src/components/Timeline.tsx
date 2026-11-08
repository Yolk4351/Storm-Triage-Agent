import { useMemo } from 'react'
import type { Frame } from '../types'

const SPEEDS = [1, 2, 5] as const     // storm hours per second

type Curve = { label: string; hours: Frame[]; color: string }
type Props = {
  curves: Curve[]                // first curve drives the time labels
  t: number
  onSeek: (t: number) => void
  playing: boolean
  onToggle: () => void
  speed: number
  onSpeed: (s: number) => void
}

const W = 1000
const H = 44

function path(values: number[], max: number) {
  if (!values.length) return ''
  const step = W / Math.max(values.length - 1, 1)
  return values.map((v, i) => `${i ? 'L' : 'M'}${(i * step).toFixed(1)},${(H - (v / max) * (H - 4)).toFixed(1)}`).join(' ')
}

const fmt = (iso: string) =>
  new Date(iso).toLocaleString('en-US', { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', timeZone: 'America/New_York' })

export default function Timeline({ curves, t, onSeek, playing, onToggle, speed, onSpeed }: Props) {
  const hours = curves[0]?.hours ?? []
  const last = Math.max(0, hours.length - 1)
  const paths = useMemo(() => {
    const max = Math.max(1, ...curves.flatMap((c) => c.hours.map((h) => h.people_at_risk)))
    return curves.map((c) => path(c.hours.map((h) => h.people_at_risk), max))
  }, [curves])
  const f = hours[t]
  const pct = last > 0 ? (t / last) * 100 : 0

  return (
    <section className="glass flex w-full max-w-[860px] items-center gap-5 rounded-[28px] px-5 py-4">
      <button
        onClick={onToggle}
        aria-label={playing ? 'Pause' : 'Play'}
        className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[var(--text)] text-[var(--bg)] transition-transform duration-200 hover:scale-105 active:scale-95"
      >
        {playing ? (
          <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="2.5" y="1.5" width="3" height="11" rx="1" /><rect x="8.5" y="1.5" width="3" height="11" rx="1" /></svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><path d="M3.5 1.8v10.4a.8.8 0 0 0 1.2.7l8.6-5.2a.8.8 0 0 0 0-1.4L4.7 1.1a.8.8 0 0 0-1.2.7Z" /></svg>
        )}
      </button>

      <div className="min-w-0 flex-1">
        <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[12px]">
          <span className="font-semibold text-[var(--text)]">{f ? fmt(f.time) : ''}</span>
          <span className="truncate tabular-nums text-[var(--text-2)]">
            {f && `${Math.round(f.weather.temp_f)}°F · gusts ${Math.round(f.weather.gust_mph)} mph · snow ${f.weather.snowfall_in.toFixed(1)} in/h`}
          </span>
        </div>
        <div className="relative h-11">
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible">
            {[...paths].reverse().map((d, i) => (
              <path key={i} d={d} fill="none" stroke={curves[curves.length - 1 - i].color} strokeWidth={i === paths.length - 1 ? 2 : 1.5} vectorEffect="non-scaling-stroke" />
            ))}
          </svg>
          <div className="pointer-events-none absolute bottom-0 top-0 w-px bg-[var(--text)]/70" style={{ left: `${pct}%` }}>
            <span className="absolute -left-[5px] -top-1 h-[11px] w-[11px] rounded-full border-2 border-[var(--pill)] bg-[var(--text)] shadow" />
          </div>
          <input
            type="range"
            min={0}
            max={last}
            value={t}
            onChange={(e) => onSeek(Number(e.target.value))}
            aria-label="Storm hour"
            className="timeline-range absolute inset-0 h-full w-full cursor-pointer"
          />
        </div>
        <div className="mt-1 flex justify-between text-[11px] text-[var(--text-3)]">
          <span>Storm starts</span>
          <span className="flex items-center gap-3">
            {curves.map((c) => (
              <span key={c.label} className="flex items-center gap-1">
                <i className="inline-block h-0.5 w-3" style={{ background: c.color }} />
                {c.label}
              </span>
            ))}
          </span>
          <span>Hour {t} of {last}</span>
        </div>
      </div>

      <div className="flex shrink-0 rounded-full bg-[var(--fill)] p-[3px] text-[12px] font-medium" role="group" aria-label="Playback speed">
        {SPEEDS.map((s) => (
          <button
            key={s}
            onClick={() => onSpeed(s)}
            className={`rounded-full px-2.5 py-1 transition-colors ${s === speed ? 'bg-[var(--pill)] text-[var(--text)] shadow-sm' : 'text-[var(--text-2)]'}`}
          >
            {s}×
          </button>
        ))}
      </div>
    </section>
  )
}
