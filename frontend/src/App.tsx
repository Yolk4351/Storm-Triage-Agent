import { useEffect, useState } from 'react'
import type { FeatureCollection } from 'geojson'
import { fitBounds } from '@math.gl/web-mercator'
import { LinearInterpolator } from '@deck.gl/core'
import { stormTitle } from './stormNames'
import { api } from './api'
import { usePlayback } from './hooks'
import type { Frame, LlmRun, Neighborhood, PolicyId, Replay, Storm, Theme, ViewMode, ViewState } from './types'
import { POLICIES } from './types'
import MapView from './components/MapView'
import { Segmented, StormPicker, ThemeToggle } from './components/Controls'
import StatsPanel, { CompareCard, CompareStrip } from './components/StatsPanel'
import Timeline from './components/Timeline'
import AiRunCard from './components/AiRunCard'
import DecisionFeed from './components/DecisionFeed'
import AiInsight from './components/AiInsight'
import { aiInsight } from './insight'

const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN as string | undefined
const BOUNDS: [[number, number], [number, number]] = [[-78.925, 42.828], [-78.775, 42.972]]

/** Camera that fits all 13 neighborhoods between the floating panels, for this window and layout. */
function fitView(mode: ViewMode): ViewState {
  const W = window.innerWidth
  const H = window.innerHeight
  const width = mode === 'compare' ? W / 2 : W
  const pad =
    mode === 'compare'
      ? { top: 230, bottom: 210, left: 24, right: 24 }
      : W >= 1280
        ? { top: 90, bottom: 170, left: 340, right: 340 }
        : W >= 1024
          ? { top: 90, bottom: 210, left: 300, right: 320 }
          : { top: 150, bottom: 230, left: 24, right: 24 }
  // never let padding swallow the map on very small windows
  const sx = Math.min(1, (width - 120) / Math.max(pad.left + pad.right, 1))
  const sy = Math.min(1, (H - 120) / Math.max(pad.top + pad.bottom, 1))
  const padding = { top: pad.top * sy, bottom: pad.bottom * sy, left: pad.left * sx, right: pad.right * sx }
  const { longitude, latitude, zoom } = fitBounds({ width, height: H, bounds: BOUNDS, padding })
  return { longitude, latitude, zoom, pitch: 0, bearing: 0 }
}
const LAYOUT_MS = 520
const EASE = 'cubic-bezier(.32,.72,0,1)'
const GLIDE = new LinearInterpolator(['longitude', 'latitude', 'zoom'])
/** fade an overlay in/out instead of mounting/unmounting it */
const fadeStyle = (show: boolean, ms = 300) => ({ opacity: show ? 1 : 0, transition: `opacity ${ms}ms ease`, pointerEvents: show ? undefined : ('none' as const) })
const fmtDay = (iso: string) => new Date(iso.replace(' ', 'T')).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem('theme')
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* storage unavailable: fall back to the system setting */
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [mode, setMode] = useState<ViewMode>('single')
  const [shapes, setShapes] = useState<FeatureCollection | null>(null)
  const [hoods, setHoods] = useState<Neighborhood[]>([])
  const [storms, setStorms] = useState<Storm[]>([])
  const [backendDown, setBackendDown] = useState(false)
  const [stormId, setStormId] = useState('dec-2022-blizzard')
  const [policy, setPolicy] = useState<PolicyId>('llm_agent')
  const [replays, setReplays] = useState<Record<string, Replay>>({})
  const [run, setRun] = useState<LlmRun | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [speed, setSpeed] = useState(2)
  const [view, setView] = useState<ViewState>(() => fitView('single'))
  const [rightMounted, setRightMounted] = useState(false)

  const storm = storms.find((s) => s.id === stormId)
  const aiReady = !!storm?.llm_available
  const baseline = replays[`${stormId}/largest_first`] ?? null
  const ai = replays[`${stormId}/llm_agent`] ?? null
  const compare = mode === 'compare'
  const needAiCard = !!storm && !aiReady && (compare || policy === 'llm_agent')
  const shown = compare ? baseline : policy === 'llm_agent' ? (aiReady ? ai : null) : baseline

  // Theme: apply to <html> and remember the choice
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('theme', theme)
    } catch {
      /* not critical */
    }
  }, [theme])

  // Static map data, plus the storm list (retried quietly until the backend is up)
  useEffect(() => {
    fetch('/data/neighborhoods.geojson').then((r) => r.json()).then(setShapes).catch(() => setToast('Map shapes missing. Run: python fetch_boundaries.py'))
    fetch('/data/neighborhoods.json').then((r) => r.json()).then(setHoods).catch(() => setToast('Neighborhood data missing. Run: python export_frontend.py'))
    let stop = false
    const load = () =>
      api
        .storms()
        .then((s) => {
          if (stop) return
          setStorms(s)
          setBackendDown(false)
        })
        .catch(() => {
          if (stop) return
          setBackendDown(true)
          setTimeout(load, 4000)
        })
    load()
    return () => {
      stop = true
    }
  }, [])

  // Load Baseline always, and the AI replay when it exists
  useEffect(() => {
    if (!storm) return
    const wanted: PolicyId[] = aiReady ? ['largest_first', 'llm_agent'] : ['largest_first']
    for (const p of wanted) {
      api
        .replay(stormId, p)
        .then((r) => setReplays((cur) => ({ ...cur, [`${stormId}/${p}`]: r })))
        .catch((e: Error) => setToast(`Could not load ${p === 'llm_agent' ? 'AI' : 'Baseline'} replay: ${e.message}`))
    }
  }, [storm, stormId, aiReady])

  // Messages disappear on their own
  useEffect(() => {
    if (!toast) return
    const id = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(id)
  }, [toast])

  // While an AI run is going, poll its progress; when it finishes, load the new replay
  useEffect(() => {
    if (run?.state !== 'running') return
    const id = setInterval(async () => {
      try {
        const s = await api.runStatus(stormId)
        setRun(s)
        if (s.state === 'done') {
          setStorms(await api.storms())
          const r = await api.replay(stormId, 'llm_agent', true)
          setReplays((cur) => ({ ...cur, [`${stormId}/llm_agent`]: r }))
        }
      } catch {
        /* transient; the next poll retries */
      }
    }, 2000)
    return () => clearInterval(id)
  }, [run?.state, stormId])

  const last = Math.max(0, (shown?.hours.length ?? baseline?.hours.length ?? 1) - 1)
  const { t, setT, playing, setPlaying, toggle } = usePlayback(last, speed)
  // Crews glide for ~90% of each storm hour, so one move ends just before the next begins
  const animMs = playing ? Math.round(Math.min(900, (0.92 * 1000) / speed)) : 0
  const frameOf = (r: Replay | null): Frame | null => r?.hours[Math.min(t, r.hours.length - 1)] ?? null

  const selectStorm = (id: string) => {
    setStormId(id)
    setT(0)
    setPlaying(false)
    setRun(storms.find((s) => s.id === id)?.llm_run ?? null)
  }
  // Layout switch: the map narrows/widens while the second map slides in, and the camera glides to fit
  const selectMode = (m: ViewMode) => {
    if (m === 'compare') setRightMounted(true)
    setMode(m)
    setView({ ...fitView(m), transitionDuration: LAYOUT_MS, transitionInterpolator: GLIDE })
  }
  const zoomBy = (d: number) => setView((v) => ({ ...v, zoom: v.zoom + d, transitionDuration: 250, transitionInterpolator: GLIDE }))
  const startRun = () => api.startRun(stormId).then(setRun).catch((e: Error) => setToast(e.message))

  if (!TOKEN) {
    return (
      <div className="grid h-full place-items-center p-8 text-center text-[var(--text-2)]">
        Missing Mapbox token: add VITE_MAPBOX_TOKEN=pk... to frontend/.env.local and restart npm run dev.
      </div>
    )
  }

  const mapProps = { token: TOKEN, theme, shapes, hoods, viewState: view, onMove: setView, animMs }
  const insight = ai && (compare || policy === 'llm_agent') ? aiInsight(ai, t, frameOf(ai)) : null
  const aiCard = storm && <AiRunCard storm={storm} run={run} error={null} onStart={startRun} />
  const curves = compare
    ? [
        { label: 'AI', hours: ai?.hours ?? [], color: 'var(--red)' },
        { label: 'Baseline', hours: baseline?.hours ?? [], color: 'var(--track)' },
      ].filter((c) => c.hours.length)
    : [
        { label: policy === 'llm_agent' ? 'AI' : 'Baseline', hours: shown?.hours ?? [], color: 'var(--red)' },
        ...(policy === 'llm_agent' && baseline ? [{ label: 'Baseline', hours: baseline.hours, color: 'var(--track)' }] : []),
      ]

  return (
    <div className="relative h-full w-full overflow-hidden bg-[var(--bg)]">
      {/* Maps: the left map narrows to half while the AI map slides in beside it (no remounting) */}
      <div className="absolute inset-0 flex">
        <div className="relative h-full shrink-0 overflow-hidden" style={{ width: compare ? '50%' : '100%', transition: `width ${LAYOUT_MS}ms ${EASE}` }}>
          <MapView {...mapProps} frame={compare ? frameOf(baseline) : frameOf(shown)} />
          <div className="absolute right-4 top-[92px] z-10" style={fadeStyle(compare)}>
            <CompareCard title="Baseline" frame={frameOf(baseline)} align="right" />
          </div>
        </div>
        <div className="relative h-full shrink-0 overflow-hidden" style={{ width: compare ? '50%' : '0%', transition: `width ${LAYOUT_MS}ms ${EASE}` }}>
          <div className="absolute inset-y-0 left-0 w-[50vw] border-l border-[var(--line)]">
            {rightMounted && <MapView {...mapProps} frame={aiReady ? frameOf(ai) : null} />}
            {aiReady ? (
              <>
                <div className="absolute left-4 top-[92px] z-10" style={fadeStyle(compare)}>
                  <CompareCard title="AI dispatcher" frame={frameOf(ai)} align="left" />
                </div>
                <div className="absolute bottom-[212px] left-1/2 z-10 -translate-x-1/2" style={fadeStyle(compare)}>
                  <AiInsight insight={insight} />
                </div>
              </>
            ) : (
              compare && <div className="fade-in absolute inset-0 z-10 grid place-items-center bg-[var(--scrim)] backdrop-blur-[2px]">{aiCard}</div>
            )}
          </div>
        </div>
      </div>

      {/* Title (single view only; the compare view keeps the center clear) */}
      {(
        <header className="glass absolute left-5 top-[68px] z-10 w-[260px] rounded-[28px] p-5 xl:top-5 xl:w-[300px]" style={fadeStyle(!compare)}>
          <p className="text-[12px] font-semibold tracking-wide text-[var(--accent)]">Storm Triage</p>
          <h1 className="mt-1 text-[22px] font-semibold leading-tight tracking-tight text-[var(--text)]">{storm ? stormTitle(storm) : 'Loading…'}</h1>
          {storm && (
            <p className="mt-1 text-[12px] text-[var(--text-2)]">
              {fmtDay(storm.start)} · {storm.hours} hours
              {storm.max_gust_mph != null && ` · gusts to ${storm.max_gust_mph} mph · low ${storm.min_temp_f}°F`}
            </p>
          )}
          <p className="mt-3 hidden text-[13px] leading-relaxed text-[var(--text)] xl:block">
            Utilities can't see indoor temperatures. Given that signal, an AI dispatcher can send crews where homes are about to become unsafe.
          </p>
          <ul className="mt-4 hidden space-y-1.5 text-[12px] text-[var(--text-2)] lg:block">
            {[['var(--orange)', 'Homes without power'], ['var(--red)', 'Homes below 50°F'], ['var(--accent)', 'Repair crew']].map(([c, l]) => (
              <li key={l} className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: c }} />
                {l}
              </li>
            ))}
          </ul>
        </header>
      )}

      {/* Controls */}
      <nav
        className="glass absolute left-1/2 top-5 z-20 flex -translate-x-1/2 items-center gap-1.5 rounded-full p-1"
      >
        <StormPicker storms={storms} value={stormId} onChange={selectStorm} />
        <div
          className="overflow-hidden"
          style={{ maxWidth: compare ? 0 : 140, opacity: compare ? 0 : 1, marginRight: compare ? -6 : 0, transition: `max-width ${LAYOUT_MS}ms ${EASE}, opacity 250ms ease, margin ${LAYOUT_MS}ms ${EASE}` }}
          aria-hidden={compare}
        >
          <Segmented
            label="Dispatch policy"
            value={policy === 'rules' ? 'largest_first' : policy}
            onChange={setPolicy}
            options={POLICIES.map((p) => ({ id: p.id, label: p.label, hint: p.blurb, dim: p.id === 'llm_agent' && !aiReady }))}
            width={60}
          />
        </div>
        <Segmented
          label="Layout"
          value={mode}
          onChange={selectMode}
          options={[
            { id: 'single', label: 'Single' },
            { id: 'compare', label: 'Side by side' },
          ]}
          width={84}
        />
        <ThemeToggle theme={theme} onChange={setTheme} />
      </nav>

      {/* Single view: numbers on the right, AI prompt in the middle */}
      {shown && frameOf(shown) && (
        <div className="absolute right-5 top-[68px] z-10 hidden flex-col gap-3 md:flex xl:top-5" style={fadeStyle(!compare)}>
          <StatsPanel frame={frameOf(shown)!} replay={shown} baseline={baseline} />
          <div className="hidden lg:block [@media(max-height:820px)]:hidden">
            <DecisionFeed replay={shown} t={t} hoods={hoods} />
          </div>
        </div>
      )}
      {policy === 'llm_agent' && aiReady && (
        <div className="absolute left-1/2 top-[68px] z-10 -translate-x-1/2" style={fadeStyle(!compare)}><AiInsight insight={insight} /></div>
      )}
      {/* Zoom (both maps follow) */}
      <div className="absolute bottom-[156px] right-5 z-20 flex flex-col overflow-hidden rounded-2xl glass">
        <button onClick={() => zoomBy(1)} aria-label="Zoom in" className="grid h-9 w-9 place-items-center text-[18px] text-[var(--text)] transition-colors hover:bg-[var(--fill)]">+</button>
        <span className="mx-2 h-px bg-[var(--line)]" />
        <button onClick={() => zoomBy(-1)} aria-label="Zoom out" className="grid h-9 w-9 place-items-center text-[18px] text-[var(--text)] transition-colors hover:bg-[var(--fill)]">−</button>
      </div>
      {!compare && needAiCard && (
        <div className="fade-in absolute inset-0 z-10 grid place-items-center bg-[var(--scrim)] backdrop-blur-[2px]">{aiCard}</div>
      )}

      {/* Bottom: comparison sentence (side by side) and the timeline */}
      {curves.length > 0 && (shown || compare) && (
        <div className="absolute inset-x-0 bottom-9 z-20 flex flex-col items-center gap-3 px-5">
          {aiReady && compare && <div className="fade-in"><CompareStrip base={frameOf(baseline)} ai={frameOf(ai)} /></div>}
          <Timeline curves={curves} t={Math.min(t, last)} onSeek={setT} playing={playing} onToggle={toggle} speed={speed} onSpeed={setSpeed} />
        </div>
      )}

      {/* Notices */}
      {backendDown && (
        <div className="glass toast absolute left-1/2 top-[120px] z-30 -translate-x-1/2 rounded-full px-4 py-2 text-[12px] text-[var(--text-2)]">
          Waiting for the backend… start it with <code className="text-[var(--text)]">uvicorn server:app --port 8000</code>
        </div>
      )}
      {toast && (
        <button
          onClick={() => setToast(null)}
          className="glass toast absolute bottom-44 left-1/2 z-30 -translate-x-1/2 rounded-full px-4 py-2 text-[12px] text-[var(--bad)]"
          title="Dismiss"
        >
          {toast} <span className="ml-2 text-[var(--text-3)]">✕</span>
        </button>
      )}

      <footer className="pointer-events-none absolute bottom-2 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap text-[11px] text-[var(--text-3)]">
        Real weather, census, tree and emPOWER data · simulated outages, crews and indoor temperatures · {storm?.snow_note}
      </footer>
    </div>
  )
}
