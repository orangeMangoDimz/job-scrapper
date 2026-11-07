export interface FilterSetting {
  location: string[]
  employmentType: string[]
  workType: string[]
}

export interface ApiSetting {
  isEnabled: boolean
  locations: string[]
  isCountryWide: boolean
  delaySeconds: [number, number] | null
}

export interface SiteSetting {
  name: string
  isEnabled: boolean
  limit: number | null
  maxAgeHours: number | null
  filter: FilterSetting | null
  fields: string[] | null
  api: ApiSetting | null
}

export interface ConfigValues {
  keywords: string[]
  limit: number | null
  maxAgeHours: number | null
  filter: FilterSetting
  defaultFields: string[]
  sites: SiteSetting[]
}

export interface ConfigSnapshot {
  values: ConfigValues
  version: number
  updatedAt: string
  updatedBy: string
  isStale: boolean
  jobFields: string[]
  mandatoryFields: string[]
}

export interface ConfigVersion {
  version: number
  updatedAt: string
  updatedBy: string
  keywords: string[]
  enabledSites: string[]
}

export type SiteChanges = Partial<Omit<SiteSetting, 'name'>>

export interface ConfigChanges {
  keywords?: string[]
  limit?: number
  maxAgeHours?: number
  filter?: FilterSetting
  defaultFields?: string[]
  sites?: Record<string, SiteChanges>
}

export const EMPTY_FILTER: FilterSetting = { location: [], employmentType: [], workType: [] }

const SITE_FIELDS = ['isEnabled', 'limit', 'maxAgeHours', 'filter', 'fields', 'api'] as const

export function toOptionalNumber(value: string | number): number | null {
  return value === '' ? null : Number(value)
}

export function toDelaySeconds(min: number | null, max: number | null): [number, number] | null {
  if (min === null && max === null) {
    return null
  }
  return [min ?? (max as number), max ?? (min as number)]
}

/**
 * Keeps only the optional job fields the scraper knows. Always-saved fields are
 * added by the scraper on every run, so they are never stored. An empty known
 * list means the scraper did not send one, so nothing is dropped as unknown
 */
export function toPickedFields(
  fields: string[],
  jobFields: string[],
  mandatoryFields: string[],
): string[] {
  const isKnown = (field: string): boolean => jobFields.length === 0 || jobFields.includes(field)
  return fields.filter((field) => isKnown(field) && !mandatoryFields.includes(field))
}

const UPPERCASE_WORDS = new Set(['id', 'url'])

/** Turns a stored field name like company_id into a label like "Company ID" */
export function toJobFieldLabel(field: string): string {
  const words = field
    .split('_')
    .map((word) => (UPPERCASE_WORDS.has(word) ? word.toUpperCase() : word))
  const [first = '', ...rest] = words
  return [first.charAt(0).toUpperCase() + first.slice(1), ...rest].join(' ')
}

function isSame(first: unknown, second: unknown): boolean {
  return JSON.stringify(first) === JSON.stringify(second)
}

function toSiteChanges(site: SiteSetting, original: SiteSetting | undefined): SiteChanges {
  const changed = SITE_FIELDS.filter((field) => !isSame(site[field], original?.[field]))
  return Object.fromEntries(changed.map((field) => [field, site[field]])) as SiteChanges
}

function toSitesChanges(values: ConfigValues, original: ConfigValues): Record<string, SiteChanges> {
  const entries = values.sites.map((site): [string, SiteChanges] => [
    site.name,
    toSiteChanges(
      site,
      original.sites.find((candidate) => candidate.name === site.name),
    ),
  ])
  return Object.fromEntries(entries.filter(([, changes]) => Object.keys(changes).length > 0))
}

export function toConfigChanges(values: ConfigValues, original: ConfigValues): ConfigChanges {
  const sites = toSitesChanges(values, original)
  const isLimitKept = values.limit === null || values.limit === original.limit
  const isMaxAgeKept = values.maxAgeHours === null || values.maxAgeHours === original.maxAgeHours
  return {
    ...(isSame(values.keywords, original.keywords) ? {} : { keywords: values.keywords }),
    ...(isLimitKept ? {} : { limit: values.limit as number }),
    ...(isMaxAgeKept ? {} : { maxAgeHours: values.maxAgeHours as number }),
    ...(isSame(values.filter, original.filter) ? {} : { filter: values.filter }),
    ...(isSame(values.defaultFields, original.defaultFields)
      ? {}
      : { defaultFields: values.defaultFields }),
    ...(Object.keys(sites).length > 0 ? { sites } : {}),
  }
}

export function hasConfigChanges(changes: ConfigChanges): boolean {
  return Object.keys(changes).length > 0
}
