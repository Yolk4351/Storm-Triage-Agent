import type { Storm } from './types'

/** Display names, consistent and title-cased. The backend ids and data stay unchanged. */
const NAMES: Record<string, string> = {
  'dec-2022-blizzard': 'Christmas Blizzard',
  'jan-2024-blizzard': 'Bills Playoff Blizzard',
  'jan-2022-lake-effect': 'Lake-Effect Snowstorm',
  'jan-2020-windstorm': 'Windstorm',
  'mar-2017-windstorm': 'Windstorm',
  'jan-2014-blizzard': 'Blizzard',
  'dec-2001-lake-effect': 'Christmas Lake-Effect Storm',
}

const titleCase = (s: string) => s.replace(/\b([a-z])/g, (m) => m.toUpperCase())

const monthYear = (iso: string) =>
  new Date(iso.replace(' ', 'T')).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })

/** e.g. "Christmas Blizzard" */
export const stormTitle = (s: Storm) => NAMES[s.id] ?? titleCase(s.name)

/** e.g. "Christmas Blizzard · Dec 2022" */
export const stormLabel = (s: Storm) => `${stormTitle(s)} · ${monthYear(s.start)}`

/** Newest storm first. */
export const byNewest = (a: Storm, b: Storm) => b.start.localeCompare(a.start)
