import { useEffect, useMemo, useRef, useState } from 'react'
import type { Crew } from './types'

export type CrewDot = Crew & { pos: [number, number] }

/** Ease-in-out: start and stop gently. */
export const easeInOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2)

/** Each crew keeps the same small offset forever, so crews sharing a spot never reshuffle around it. */
function placed(c: Crew): CrewDot {
  const n = Number(c.id.match(/\d+/)?.[0] ?? 0)
  const a = (2 * Math.PI * (n % 8)) / 8
  return { ...c, pos: [c.lon + 0.0019 * Math.cos(a), c.lat + 0.0014 * Math.sin(a)] }
}

/**
 * Crew positions animated frame by frame (requestAnimationFrame), so motion is smooth no matter how the map
 * redraws. A new target starts from wherever each dot is right now, so an interrupted glide never jumps.
 */
export function useCrewMotion(crews: Crew[], ms: number): CrewDot[] {
  const targets = useMemo(() => crews.map(placed), [crews])
  const [shown, setShown] = useState<CrewDot[]>(targets)
  const current = useRef<CrewDot[]>(targets)

  useEffect(() => {
    const from = current.current
    const byId = Object.fromEntries(from.map((d) => [d.id, d.pos]))
    const start = performance.now()
    let raf = 0
    const step = (now: number) => {
      const k = ms > 0 ? Math.min(1, (now - start) / ms) : 1
      const e = easeInOut(k)
      const next = targets.map((d) => {
        const p = byId[d.id]
        return p ? { ...d, pos: [p[0] + (d.pos[0] - p[0]) * e, p[1] + (d.pos[1] - p[1]) * e] as [number, number] } : d
      })
      current.current = next
      setShown(next)
      if (k < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [targets, ms])

  return shown
}
