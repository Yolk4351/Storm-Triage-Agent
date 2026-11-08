import { useState } from 'react'
import type { LlmRun, Storm } from '../types'

type Props = { storm: Storm; run: LlmRun | null; error: string | null; onStart: () => void }

export default function AiRunCard({ storm, run, error, onStart }: Props) {
  const [confirming, setConfirming] = useState(false)
  const running = run?.state === 'running'
  const pct = run && run.hours ? Math.round((run.hour / run.hours) * 100) : 0

  return (
    <section className="glass w-[360px] rounded-[28px] p-6 text-center">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[var(--accent)]/10 text-[var(--accent)]">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />
          <circle cx="12" cy="12" r="3.2" />
        </svg>
      </div>
      <h2 className="mt-4 text-[17px] font-semibold text-[var(--text)]">
        {running ? 'The AI is dispatching…' : 'No AI run for this storm yet'}
      </h2>
      <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--text-2)]">
        {running
          ? `Claude is deciding hour by hour. ${run?.message ?? ''}`
          : `Claude would dispatch crews through all ${storm.hours} hours of the ${storm.name}. This calls the Claude API.`}
      </p>

      {running ? (
        <div className="mt-5">
          <div className="h-1.5 overflow-hidden rounded-full bg-[var(--line)]">
            <div className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-700 ease-out" style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-2 text-[12px] tabular-nums text-[var(--text-3)]">{pct}%</p>
        </div>
      ) : confirming ? (
        <div className="mt-5 flex gap-2">
          <button onClick={() => setConfirming(false)} className="h-10 flex-1 rounded-full bg-[var(--fill)] text-[14px] font-medium text-[var(--text)] transition-colors hover:bg-[var(--fill-hover)]">
            Cancel
          </button>
          <button
            onClick={() => {
              setConfirming(false)
              onStart()
            }}
            className="h-10 flex-1 rounded-full bg-[var(--accent)] text-[14px] font-medium text-white transition-colors hover:bg-[var(--accent-hover)]"
          >
            Confirm run
          </button>
        </div>
      ) : (
        <button
          onClick={() => setConfirming(true)}
          className="mt-5 h-10 w-full rounded-full bg-[var(--accent)] text-[14px] font-medium text-white transition-colors hover:bg-[var(--accent-hover)]"
        >
          Run AI · about ${storm.llm_cost_estimate_usd.toFixed(2)}
        </button>
      )}

      {(error || run?.state === 'error') && <p className="mt-3 text-[12px] text-[var(--bad)]">{error ?? run?.message}</p>}
      {storm.llm_hours_cached > 0 && !running && (
        <p className="mt-3 text-[11px] text-[var(--text-3)]">{storm.llm_hours_cached} of {storm.hours} hours already done; it will resume.</p>
      )}
    </section>
  )
}
