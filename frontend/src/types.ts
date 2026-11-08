export type PolicyId = 'largest_first' | 'rules' | 'llm_agent'
export type Theme = 'light' | 'dark'
export type ViewMode = 'single' | 'compare'

/** Policies offered in the UI. `rules` still exists in the backend for the evaluation, but is not shown. */
export const POLICIES: { id: PolicyId; label: string; blurb: string }[] = [
  { id: 'largest_first', label: 'Baseline', blurb: 'Largest outage first' },
  { id: 'llm_agent', label: 'AI', blurb: 'Claude as dispatcher' },
]
export const policyLabel = (p: PolicyId) => POLICIES.find((x) => x.id === p)?.label ?? p

export type LlmRun = { state: 'idle' | 'running' | 'done' | 'error'; hour: number; hours: number; message: string }

export type Storm = {
  id: string
  name: string
  start: string
  end: string
  hours: number
  llm_available: boolean
  llm_hours_cached: number
  llm_cost_estimate_usd: number
  snow_note: string
  max_gust_mph?: number
  min_temp_f?: number
  model_snow_in?: number
  llm_run?: LlmRun | null
}

export type HoodState = {
  out: number
  below50: number
  temp: number
  risk: number
  share_out: number
  people_at_risk: number
}

export type Crew = { id: string; status: 'idle' | 'moving' | 'repairing'; target: string | null; lat: number; lon: number }

export type Frame = {
  t: number
  time: string
  weather: { temp_f: number; wind_mph: number; gust_mph: number; snowfall_in: number }
  people_at_risk: number
  elderly_at_risk: number
  homes_out: number
  person_hours_at_risk: number
  hoods: Record<string, HoodState>
  crews: Crew[]
  grid_signal_pct?: number
  note?: string
}

export type Replay = {
  storm: { id: string; name: string; start: string; end: string; hours: number }
  policy: PolicyId
  summary: {
    person_hours_at_risk: number
    elderly_person_hours_at_risk: number
    peak_people_at_risk: number
    household_hours_out: number
    peak_households_out: number
  }
  hours: Frame[]
  events: { t: number; crew: string; hood: string; action: string; reason: string }[]
}

export type Neighborhood = { id: string; name: string; lat: number; lon: number; households: number; age_65_plus_share: number }

export type ViewState = {
  longitude: number
  latitude: number
  zoom: number
  pitch: number
  bearing: number
  /** set when the camera should glide to this view instead of jumping */
  transitionDuration?: number
  transitionInterpolator?: unknown
}
