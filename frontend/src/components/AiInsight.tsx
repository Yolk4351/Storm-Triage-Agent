import type { Insight } from '../insight'

/** Small floating bubble: what the AI is doing right now, and why (in its own words). */
export default function AiInsight({ insight }: { insight: Insight | null }) {
  if (!insight) return null
  return (
    <div key={insight.headline} className="glass toast pointer-events-none flex max-w-[360px] items-start gap-2.5 rounded-2xl px-3.5 py-2.5">
      <span className="mt-[3px] grid h-5 w-5 shrink-0 place-items-center rounded-full bg-[var(--accent)]/15 text-[var(--accent)]">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2.5l1.9 5.6 5.6 1.9-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.9L12 2.5Zm6.5 12l.9 2.6 2.6.9-2.6.9-.9 2.6-.9-2.6-2.6-.9 2.6-.9.9-2.6Z" />
        </svg>
      </span>
      <div className="min-w-0">
        <p className="text-[13px] font-semibold leading-snug text-[var(--text)]">{insight.headline}</p>
        {insight.detail && <p className="mt-0.5 line-clamp-2 text-[12px] leading-snug text-[var(--text-2)] transition-opacity duration-300">“{insight.detail}”</p>}
      </div>
    </div>
  )
}
