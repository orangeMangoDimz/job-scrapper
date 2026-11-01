export interface SiteSetting {
  name: string
  isEnabled: boolean
  limit: number | null
}

export interface ConfigValues {
  keywords: string[]
  limit: number | null
  maxAgeHours: number | null
  proxyUrl: string | null
  sites: SiteSetting[]
}

export interface ConfigSnapshot {
  values: ConfigValues
  isReadOnly: boolean
  locked: string[]
  isStale: boolean
}

export interface SiteChanges {
  isEnabled?: boolean
  limit?: number
}

export interface ConfigChanges {
  keywords?: string[]
  limit?: number
  maxAgeHours?: number
  proxyUrl?: string | null
  sites?: Record<string, SiteChanges>
}

export function isLocked(locked: string[], path: string): boolean {
  return locked.includes(path)
}

export function toOptionalNumber(value: string | number): number | null {
  return value === '' ? null : Number(value)
}

function isSameList(first: string[], second: string[]): boolean {
  return first.length === second.length && first.every((item, index) => item === second[index])
}

function toSiteChanges(
  site: SiteSetting,
  original: SiteSetting | undefined,
  locked: string[],
): SiteChanges {
  const isEnabledKept =
    site.isEnabled === original?.isEnabled || isLocked(locked, `sites.${site.name}.enabled`)
  const isLimitKept =
    site.limit === null ||
    site.limit === original?.limit ||
    isLocked(locked, `sites.${site.name}.limit`)
  return {
    ...(isEnabledKept ? {} : { isEnabled: site.isEnabled }),
    ...(isLimitKept ? {} : { limit: site.limit as number }),
  }
}

function toSitesChanges(
  values: ConfigValues,
  original: ConfigValues,
  locked: string[],
): Record<string, SiteChanges> {
  const entries = values.sites.map((site): [string, SiteChanges] => [
    site.name,
    toSiteChanges(
      site,
      original.sites.find((candidate) => candidate.name === site.name),
      locked,
    ),
  ])
  return Object.fromEntries(entries.filter(([, changes]) => Object.keys(changes).length > 0))
}

export function toConfigChanges(
  values: ConfigValues,
  original: ConfigValues,
  locked: string[],
): ConfigChanges {
  const sites = toSitesChanges(values, original, locked)
  const isKeywordsKept =
    isSameList(values.keywords, original.keywords) || isLocked(locked, 'keywords')
  const isLimitKept =
    values.limit === null || values.limit === original.limit || isLocked(locked, 'limit')
  const isMaxAgeKept =
    values.maxAgeHours === null ||
    values.maxAgeHours === original.maxAgeHours ||
    isLocked(locked, 'max_age_hours')
  const isProxyKept = values.proxyUrl === original.proxyUrl || isLocked(locked, 'proxy')
  return {
    ...(isKeywordsKept ? {} : { keywords: values.keywords }),
    ...(isLimitKept ? {} : { limit: values.limit as number }),
    ...(isMaxAgeKept ? {} : { maxAgeHours: values.maxAgeHours as number }),
    ...(isProxyKept ? {} : { proxyUrl: values.proxyUrl }),
    ...(Object.keys(sites).length > 0 ? { sites } : {}),
  }
}

export function hasConfigChanges(changes: ConfigChanges): boolean {
  return Object.keys(changes).length > 0
}
