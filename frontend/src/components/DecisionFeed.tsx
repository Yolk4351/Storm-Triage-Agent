import type { Neighborhood, Replay } from '../types'

type Props = { replay: Replay; t: number; hoods: Neighborhood[] }

export default function DecisionFeed({ replay, t, hoods }: Props) {
  const names = Object.fromEntries(hoods.map((h) => [h.id, h.name]))
  const recent = replay.events.filter((e) => e.t <= t).slice(-4).reverse()
  const note = replay.policy === 'llm_agent' ? [...replay.hours.slice(0, t + 1)].reverse().find((h) => h.note && !h.note.startsWith('Skipped'))?.note : null

  return (
    <section className="glass w-[300px] rounded-[28px] p-5">
      <p className="text-[13px] font-semibold text-[var(--text)]">{replay.policy === 'llm_agent' ? 'Why the AI did it' : 'Latest dispatches'}</p>
      {note && <p className="mt-2 line-clamp-4 text-[12px] leading-relaxed text-[var(--text)]">{note}</p>}
      <ul className="mt-3 space-y-2.5">
        {recent.length === 0 && <li className="text-[12px] text-[var(--text-3)]">No dispatches yet.</li>}
        {recent.map((e) => (
          <li key={`${e.t}-${e.crew}-${e.hood}-${e.action}`} className="feed-item text-[12px] leading-snug">
            <p className="font-medium text-[var(--text)]">
              {e.action === 'alert' ? 'Alert' : e.crew.replace('crew-', 'Crew ')} → {names[e.hood] ?? e.hood}
              <span className="ml-1.5 font-normal text-[var(--text-3)]">h{e.t}</span>
            </p>
            <p className="mt-0.5 line-clamp-2 text-[var(--text-2)]">{e.reason}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}
