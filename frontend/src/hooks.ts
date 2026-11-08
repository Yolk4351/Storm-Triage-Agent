import { useEffect, useRef, useState } from 'react'

/** Smoothly animates a number toward its target (ease-out), for counters. */
export function useTween(target: number, ms = 450) {
  const [value, setValue] = useState(target)
  const from = useRef(target)
  const shown = useRef(target)

  useEffect(() => {
    from.current = shown.current
    const start = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / ms)
      const eased = 1 - Math.pow(1 - k, 3)
      shown.current = from.current + (target - from.current) * eased
      setValue(shown.current)
      if (k < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])

  return value
}

/** Plays an hour index from 0..last at `hoursPerSecond`, stopping at the end. */
export function usePlayback(last: number, hoursPerSecond: number) {
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => {
      setT((cur) => {
        if (cur >= last) {
          setPlaying(false)
          return cur
        }
        return cur + 1
      })
    }, 1000 / hoursPerSecond)
    return () => clearInterval(id)
  }, [playing, last, hoursPerSecond])

  const toggle = () => {
    if (!playing && t >= last) setT(0)
    setPlaying((p) => !p)
  }
  return { t: Math.min(t, last), setT, playing, setPlaying, toggle }
}
