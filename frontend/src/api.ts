import type { LlmRun, PolicyId, Replay, Storm } from './types'

async function get<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (!r.ok) {
    const body = await r.json().catch(() => ({}))
    throw new Error(body.detail ?? `HTTP ${r.status}`)
  }
  return r.json() as Promise<T>
}

const replays = new Map<string, Promise<Replay>>()

export const api = {
  storms: () => get<Storm[]>('/api/storms'),
  replay: (storm: string, policy: PolicyId, fresh = false) => {
    const key = `${storm}/${policy}`
    if (fresh || !replays.has(key)) {
      const p = get<Replay>(`/api/replay/${storm}/${policy}`)
      p.catch(() => replays.delete(key))
      replays.set(key, p)
    }
    return replays.get(key)!
  },
  runStatus: (storm: string) => get<LlmRun>(`/api/llm-runs/${storm}`),
  startRun: (storm: string) => get<LlmRun>(`/api/llm-runs/${storm}`, { method: 'POST' }),
}
