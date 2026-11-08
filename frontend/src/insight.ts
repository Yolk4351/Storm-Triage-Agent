import type { Frame, Replay } from './types'

export type Insight = { headline: string; detail: string | null }

type Event = Replay['events'][number]

// Short headline per kind of decision, matched against Claude's own one-sentence reasons (highest priority first).
const PATTERNS: [RegExp, string][] = [
  [/already[- ]cold|already below|at 50°f now|below 50°f now/i, 'Restoring homes that are already dangerously cold'],
  [/medical/i, 'Prioritizing homes with medical-device users'],
  [/go(es|ing)? cold|drop|below 50°f in|to 50°f|near the 50|before the repair|about to/i, 'Racing to restore homes before they drop below 50°F'],
  [/largest|most people|population/i, 'Restoring power to the most people at once'],
  [/fastest|shortest|soonest|closest|nearest/i, 'Sending the crew that can finish fastest'],
]
const HOSPITAL = /hospital|medical center|ecmc|roswell|oishei|buffalo general|mercy|\bva\b/i

const tidy = (s: string) => {
  const t = s.replace(/crew-(\d+)/gi, 'Crew $1').replace(/\s+/g, ' ').trim()
  return t.length > 120 ? `${t.slice(0, 117).trimEnd()}…` : t
}

const usable = (e: Event) => !HOSPITAL.test(e.reason)

/** Headline for the hour's decisions, plus the reason that actually backs that headline. */
function summarize(events: Event[]): Insight {
  const staged = events.filter((e) => e.action === 'staged')
  if (staged.length) {
    const r = staged.find(usable)
    return { headline: 'Moving crews into position ahead of forecast outages', detail: r ? tidy(r.reason) : null }
  }
  const dispatched = events.filter((e) => e.action === 'dispatched')
  if (!dispatched.length) {
    const r = events.find(usable)
    return { headline: 'Alerting residents to warming shelters', detail: r ? tidy(r.reason) : null }
  }
  const count = dispatched.length > 1 ? ` · ${dispatched.length} crews` : ''
  for (const [re, headline] of PATTERNS) {
    const backing = dispatched.filter((e) => re.test(e.reason))
    if (backing.length) {
      const r = backing.find(usable)
      return { headline: headline + count, detail: r ? tidy(r.reason) : null }
    }
  }
  const r = dispatched.find(usable)
  return { headline: 'Dispatching crews to the most urgent outages' + count, detail: r ? tidy(r.reason) : null }
}

/** A one-line, human summary of what the AI decided around hour t, plus one of its real reasons. */
export function aiInsight(replay: Replay, t: number, frame: Frame | null): Insight | null {
  if (replay.policy !== 'llm_agent') return null
  // Show the latest decision for a couple of hours so it doesn't flicker away between decisions
  for (let back = 0; back <= 2; back++) {
    const events = replay.events.filter((e) => e.t === t - back)
    if (events.length) return summarize(events)
  }
  if (!frame) return null
  if (frame.homes_out === 0) return { headline: 'Watching the storm with crews on standby', detail: null }
  if (frame.crews.every((c) => c.status !== 'idle')) return { headline: 'Every crew is busy on a repair', detail: null }
  return null
}
