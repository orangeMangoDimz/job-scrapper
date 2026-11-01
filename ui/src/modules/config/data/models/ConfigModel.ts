import type { ConfigChanges, ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'

export interface ConfigModel {
  values: {
    keywords: string[]
    limit: number | null
    max_age_hours: number | null
    proxy_url: string | null
    sites: { name: string; enabled: boolean; limit: number | null }[]
  }
  read_only: boolean
  locked: string[]
  is_stale: boolean
}

export interface ConfigChangesModel {
  keywords?: string[]
  limit?: number
  max_age_hours?: number
  proxy_url?: string | null
  sites?: Record<string, { enabled?: boolean; limit?: number }>
}

export function toConfigSnapshot(model: ConfigModel): ConfigSnapshot {
  return {
    values: {
      keywords: model.values.keywords,
      limit: model.values.limit,
      maxAgeHours: model.values.max_age_hours,
      proxyUrl: model.values.proxy_url,
      sites: model.values.sites.map((site) => ({
        name: site.name,
        isEnabled: site.enabled,
        limit: site.limit,
      })),
    },
    isReadOnly: model.read_only,
    locked: model.locked,
    isStale: model.is_stale,
  }
}

export function toConfigChangesModel(changes: ConfigChanges): ConfigChangesModel {
  const { maxAgeHours, proxyUrl, sites, ...shared } = changes
  return {
    ...shared,
    ...(maxAgeHours === undefined ? {} : { max_age_hours: maxAgeHours }),
    ...(proxyUrl === undefined ? {} : { proxy_url: proxyUrl }),
    ...(sites === undefined
      ? {}
      : {
          sites: Object.fromEntries(
            Object.entries(sites).map(([name, { isEnabled, limit }]) => [
              name,
              {
                ...(isEnabled === undefined ? {} : { enabled: isEnabled }),
                ...(limit === undefined ? {} : { limit }),
              },
            ]),
          ),
        }),
  }
}
