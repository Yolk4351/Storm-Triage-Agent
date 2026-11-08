import { useTween } from '../hooks'
import type { Frame, Replay } from '../types'
import { policyLabel } from '../types'

function Big({ label, value, tone, hint, size = 34 }: { label: string; value: number; tone: string; hint?: string; size?: number }) {
  const v = useTween(value)
  return (
    <div>
      <p className="text-[12px] font-medium text-[var(--text-2)]">{label}</p>
      <p className="mt-0.5 font-semibold leading-none tracking-tight tabular-nums" style={{ color: tone, fontSize: size }}>
        {Math.round(v).toLocaleString()}
      </p>
      {hint && <p className="mt-1 text-[11px] text-[var(--text-3)]">{hint}</p>}
    </div>
  )
}

function Small({ label, value }: { label: string; value: number }) {
  const v = useTween(value)
  return (
    <div className="flex items-baseline justify-between gap-4 text-[13px]">
      <span className="text-[var(--text-2)]">{label}</span>
      <span className="font-medium tabular-nums text-[var(--text)]">{Math.round(v).toLocaleString()}</span>
    </div>
  )
}

/** Single view: the panel on the right. */
export default function StatsPanel({ frame, replay, baseline }: { frame: Frame; replay: Replay; baseline: Replay | null }) {
  const base = baseline?.hours[frame.t]
  const showDelta = replay.policy !== 'largest_first' && !!base && base.person_hours_at_risk > 0
  const delta = showDelta ? (frame.person_hours_at_risk - base.person_hours_at_risk) / base.person_hours_at_risk : 0

  return (
    <section className="glass w-[300px] rounded-[28px] p-6">
      <div className="flex items-center justify-between">
        <p className="text-[13px] font-semibold text-[var(--text)]">Right now</p>
        <span className="rounded-full bg-[var(--fill)] px-2.5 py-0.5 text-[11px] font-medium text-[var(--text-2)]">{policyLabel(replay.policy)}</span>
      </div>
      <div className="mt-5 space-y-5">
        <Big label="People at risk" value={frame.people_at_risk} tone="var(--red)" hint="In homes below 50°F" />
        <Big label="Elderly at risk" value={frame.elderly_at_risk} tone="var(--orange)" hint="Estimated, residents 65+" />
      </div>
      <div className="mt-6 space-y-2 border-t border-[var(--line)] pt-4">
        <Small label="Homes without power" value={frame.homes_out} />
        <Small label="Person-hours at risk so far" value={frame.person_hours_at_risk} />
      </div>
      <div className={`overflow-hidden transition-all duration-500 ${showDelta ? 'mt-4 max-h-20 opacity-100' : 'max-h-0 opacity-0'}`}>
        <DeltaChip delta={delta} />
      </div>
    </section>
  )
}

export function DeltaChip({ delta }: { delta: number }) {
  const good = delta <= 0
  return (
    <div className="rounded-2xl px-3.5 py-2.5 text-[13px]" style={{ background: good ? 'var(--good-bg)' : 'var(--bad-bg)', color: good ? 'var(--good)' : 'var(--bad)' }}>
      <span className="font-semibold tabular-nums">
        {good ? '−' : '+'}
        {Math.abs(Math.round(delta * 100))}%
      </span>{' '}
      person-hours at risk vs Baseline so far
    </div>
  )
}

/** Side-by-side view: compact numbers for one map, placed next to the center divider. */
export function CompareCard({ title, frame, align }: { title: string; frame: Frame | null; align: 'left' | 'right' }) {
  const elderly = useTween(frame?.elderly_at_risk ?? 0)
  return (
    <section className={`glass w-[176px] rounded-[20px] px-3.5 py-3 ${align === 'right' ? 'text-right' : ''}`}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-2)]">{title}</p>
      <div className="mt-1.5">
        <Big label="People at risk" value={frame?.people_at_risk ?? 0} tone="var(--red)" size={26} />
      </div>
      <p className="mt-1.5 text-[12px] tabular-nums text-[var(--text-2)]">
        <span className="font-semibold text-[var(--orange)]">{Math.round(elderly).toLocaleString()}</span> elderly at risk
      </p>
      <p className="text-[11px] tabular-nums text-[var(--text-3)]">{(frame?.homes_out ?? 0).toLocaleString()} homes without power</p>
    </section>
  )
}

/** Side-by-side view: the one sentence that matters, in the middle of the screen. */
export function CompareStrip({ base, ai }: { base: Frame | null; ai: Frame | null }) {
  const now = (base?.people_at_risk ?? 0) - (ai?.people_at_risk ?? 0)
  const fewerNow = useTween(Math.max(now, 0))
  const cumBase = base?.person_hours_at_risk ?? 0
  const delta = cumBase > 0 && ai ? (ai.person_hours_at_risk - cumBase) / cumBase : null
  return (
    <section className="glass flex items-center gap-4 rounded-full px-5 py-2.5 text-[13px]">
      <span className="text-[var(--text-2)]">AI vs Baseline</span>
      <span className="h-4 w-px bg-[var(--line)]" />
      <span className="tabular-nums text-[var(--text)]">
        <b className="font-semibold" style={{ color: now > 0 ? 'var(--good)' : 'var(--text)' }}>{Math.round(fewerNow).toLocaleString()}</b> fewer people at risk now
      </span>
      {delta !== null && (
        <>
          <span className="h-4 w-px bg-[var(--line)]" />
          <span className="tabular-nums" style={{ color: delta <= 0 ? 'var(--good)' : 'var(--bad)' }}>
            <b className="font-semibold">{delta <= 0 ? '−' : '+'}{Math.abs(Math.round(delta * 100))}%</b> person-hours so far
          </span>
        </>
      )}
    </section>
  )
}
