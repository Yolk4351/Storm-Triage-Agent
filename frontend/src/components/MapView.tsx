import { useEffect, useMemo, useRef, useState } from 'react'
import DeckGL from '@deck.gl/react'
import type { TransitionInterpolator } from '@deck.gl/core'
import Map from 'react-map-gl/mapbox'
import type { MapRef } from 'react-map-gl/mapbox'
import { GeoJsonLayer, ScatterplotLayer } from '@deck.gl/layers'
import type { Feature, FeatureCollection, Geometry } from 'geojson'
import 'mapbox-gl/dist/mapbox-gl.css'
import type { Frame, Neighborhood, Theme, ViewState } from '../types'
import { easeInOut, useCrewMotion } from '../crewMotion'
import type { CrewDot } from '../crewMotion'

type Props = {
  token: string
  theme: Theme
  shapes: FeatureCollection | null
  hoods: Neighborhood[]
  frame: Frame | null
  viewState: ViewState
  onMove: (v: ViewState) => void
  animMs: number            // how long crews/colors glide between hours (0 = jump, e.g. while scrubbing)
}
type HoodProps = { id: string; name: string }
type RGBA = [number, number, number, number]

const OUT: [number, number, number] = [255, 159, 10]      // Apple system orange
const COLD: [number, number, number] = [255, 59, 48]      // Apple system red
const THEME_MS = 350
const STYLE: Record<Theme, string> = {
  light: 'mapbox://styles/mapbox/light-v11',
  dark: 'mapbox://styles/mapbox/dark-v11',
}

/** Orange = homes without power, shifting to red as those homes drop below 50°F. */
function hoodColor(out: number, below50: number, households: number, calm: RGBA): RGBA {
  if (!out) return calm
  const share = Math.min(1, out / households)
  const cold = Math.min(1, below50 / out)
  const mix = (a: number, b: number) => Math.round(a + (b - a) * cold)
  return [mix(OUT[0], COLD[0]), mix(OUT[1], COLD[1]), mix(OUT[2], COLD[2]), Math.round(70 + 165 * Math.sqrt(share))]
}

/**
 * Two basemaps (light and dark) stay loaded and stacked; switching theme is just a cross-fade of their
 * opacity, so nothing reloads and nothing flashes. Neighborhoods and crews are drawn by deck.gl on its own
 * canvas above both, in a fixed order (crews always on top), and deck.gl handles pan/zoom for all of them.
 */
export default function MapView({ token, theme, shapes, hoods, frame, viewState, onMove, animMs }: Props) {
  const [hover, setHover] = useState<{ id: string; x: number; y: number } | null>(null)
  const byId = useMemo(() => Object.fromEntries(hoods.map((h) => [h.id, h])), [hoods])
  const dark = theme === 'dark'
  const dots = useCrewMotion(frame?.crews ?? [], animMs)
  const hourKey = frame ? frame.t : -1
  const { transitionDuration, transitionInterpolator, ...camera } = viewState

  // Mapbox only notices window resizes, not its container shrinking (e.g. full width -> half when switching to
  // side by side). Without this the basemap keeps its old size and drifts out of line with the neighborhoods.
  const root = useRef<HTMLDivElement>(null)
  const maps = useRef<Record<string, MapRef | null>>({})
  useEffect(() => {
    const el = root.current
    if (!el) return
    const ro = new ResizeObserver(() => Object.values(maps.current).forEach((m) => m?.getMap().resize()))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const areas = useMemo(() => {
    if (!shapes) return null
    const calm: RGBA = dark ? [255, 255, 255, 18] : [120, 100, 70, 24]
    return new GeoJsonLayer<HoodProps>({
      id: 'areas',
      data: shapes as FeatureCollection<Geometry, HoodProps>,
      filled: true,
      stroked: true,
      pickable: true,
      getFillColor: (f: Feature<Geometry, HoodProps>) => {
        const s = frame?.hoods[f.properties.id]
        return s ? hoodColor(s.out, s.below50, byId[f.properties.id]?.households ?? 1, calm) : calm
      },
      getLineColor: dark ? [255, 255, 255, 60] : [255, 250, 240, 230],
      getLineWidth: 1.5,
      lineWidthUnits: 'pixels',
      transitions: {
        getFillColor: { duration: Math.max(animMs, THEME_MS), easing: easeInOut },
        getLineColor: { duration: THEME_MS, easing: easeInOut },
      },
      updateTriggers: { getFillColor: [hourKey, theme], getLineColor: theme },
      onHover: (info) => setHover(info.object ? { id: info.object.properties.id, x: info.x, y: info.y } : null),
    })
  }, [shapes, frame, byId, dark, theme, animMs, hourKey])

  const crews = new ScatterplotLayer<CrewDot>({
    id: 'crews',
    data: dots,                      // positions already animated by useCrewMotion, every frame
    getPosition: (c) => c.pos,
    getRadius: (c) => (c.status === 'idle' ? 4.5 : 6),
    radiusUnits: 'pixels',
    getFillColor: (c) => (c.status === 'idle' ? [142, 142, 147, 210] : dark ? [10, 132, 255, 255] : [0, 113, 227, 240]),
    getLineColor: dark ? [0, 0, 0, 220] : [255, 252, 245, 255],
    getLineWidth: 2,
    lineWidthUnits: 'pixels',
    stroked: true,
    transitions: {
      getFillColor: { duration: THEME_MS, easing: easeInOut },
      getRadius: { duration: 350, easing: easeInOut },
      getLineColor: { duration: THEME_MS, easing: easeInOut },
    },
    updateTriggers: { getFillColor: [hourKey, theme], getRadius: hourKey, getLineColor: theme },
  })

  const s = hover && frame?.hoods[hover.id]
  const h = hover && byId[hover.id]

  return (
    <div ref={root} className="absolute inset-0">
      {(['light', 'dark'] as Theme[]).map((t) => (
        <div
          key={t}
          className="absolute inset-0 transition-opacity ease-in-out"
          style={{ opacity: theme === t ? 1 : 0, transitionDuration: `${THEME_MS}ms` }}
          aria-hidden={theme !== t}
        >
          <Map ref={(m) => { maps.current[t] = m }} {...camera} interactive={false} mapboxAccessToken={token} mapStyle={STYLE[t]} style={{ width: '100%', height: '100%' }} />
        </div>
      ))}
      <div className="map-tint pointer-events-none absolute inset-0" aria-hidden />
      <DeckGL
        viewState={{ ...camera, transitionDuration, transitionInterpolator: transitionInterpolator as TransitionInterpolator | undefined }}
        controller={{ dragRotate: false, touchRotate: false, doubleClickZoom: true }}
        onViewStateChange={({ viewState: v }) => {
          const { longitude, latitude, zoom, pitch, bearing } = v as ViewState
          onMove({ longitude, latitude, zoom, pitch, bearing })
        }}
        layers={areas ? [areas, crews] : [crews]}
        style={{ position: 'absolute', inset: '0' }}
      />
      {hover && h && (
        <div className="glass pointer-events-none absolute z-20 w-56 rounded-2xl px-4 py-3 text-[13px]" style={{ left: hover.x + 14, top: hover.y + 14 }}>
          <p className="font-semibold text-[var(--text)]">{h.name}</p>
          <div className="mt-1.5 space-y-0.5 text-[var(--text-2)]">
            <Row k="Homes" v={h.households.toLocaleString()} />
            <Row k="Without power" v={(s?.out ?? 0).toLocaleString()} />
            <Row k="People at risk" v={(s?.people_at_risk ?? 0).toLocaleString()} strong={!!s?.people_at_risk} />
            <Row k="Residents 65+" v={`${Math.round(h.age_65_plus_share * 100)}%`} />
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ k, v, strong }: { k: string; v: string; strong?: boolean }) {
  return (
    <div className="flex justify-between">
      <span>{k}</span>
      <span className={strong ? 'font-semibold text-[var(--red)]' : 'text-[var(--text)]'}>{v}</span>
    </div>
  )
}
