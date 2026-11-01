import type {
  ApiSetting,
  ConfigChanges,
  ConfigSnapshot,
  ConfigVersion,
  FilterSetting,
  SiteChanges,
  SiteSetting,
} from '@/modules/config/domain/entities/ScraperConfig'

export interface FilterModel {
  location?: string[]
  employment_type?: string[]
  work_type?: string[]
}

export interface ApiModel {
  enabled?: boolean
  locations?: string[]
  country_wide?: boolean
  delay_seconds?: [number, number] | null
}

export interface SiteModel {
  name: string
  enabled: boolean
  limit: number | null
  max_age_hours: number | null
  filter: FilterModel | null
  fields: string[] | null
  api: ApiModel | null
}

export interface ConfigModel {
  values: {
    keywords: string[]
    limit: number | null
    max_age_hours: number | null
    filter: FilterModel
    default_fields: string[]
    sites: SiteModel[]
  }
  version: number
  updated_at: string
  updated_by: string
  is_stale: boolean
}

export interface SiteChangesModel {
  enabled?: boolean
  limit?: number | null
  max_age_hours?: number | null
  filter?: FilterModel | null
  fields?: string[] | null
  api?: ApiModel | null
}

export interface ConfigChangesModel {
  keywords?: string[]
  limit?: number
  max_age_hours?: number
  filter?: FilterModel
  default_fields?: string[]
  sites?: Record<string, SiteChangesModel>
}

export interface ConfigHistoryModel {
  entries: {
    version: number
    updated_at: string
    updated_by: string
    keywords: string[]
    enabled_sites: string[]
  }[]
}

function toFilterSetting(model: FilterModel): FilterSetting {
  return {
    location: model.location ?? [],
    employmentType: model.employment_type ?? [],
    workType: model.work_type ?? [],
  }
}

function toApiSetting(model: ApiModel): ApiSetting {
  return {
    isEnabled: model.enabled ?? true,
    locations: model.locations ?? [],
    isCountryWide: model.country_wide ?? false,
    delaySeconds: model.delay_seconds ?? null,
  }
}

function toSiteSetting(model: SiteModel): SiteSetting {
  return {
    name: model.name,
    isEnabled: model.enabled,
    limit: model.limit,
    maxAgeHours: model.max_age_hours,
    filter: model.filter === null ? null : toFilterSetting(model.filter),
    fields: model.fields,
    api: model.api === null ? null : toApiSetting(model.api),
  }
}

export function toConfigSnapshot(model: ConfigModel): ConfigSnapshot {
  return {
    values: {
      keywords: model.values.keywords,
      limit: model.values.limit,
      maxAgeHours: model.values.max_age_hours,
      filter: toFilterSetting(model.values.filter),
      defaultFields: model.values.default_fields,
      sites: model.values.sites.map(toSiteSetting),
    },
    version: model.version,
    updatedAt: model.updated_at,
    updatedBy: model.updated_by,
    isStale: model.is_stale,
  }
}

export function toConfigVersions(model: ConfigHistoryModel): ConfigVersion[] {
  return model.entries.map((entry) => ({
    version: entry.version,
    updatedAt: entry.updated_at,
    updatedBy: entry.updated_by,
    keywords: entry.keywords,
    enabledSites: entry.enabled_sites,
  }))
}

function toFilterModel(filter: FilterSetting): FilterModel {
  return {
    ...(filter.location.length > 0 ? { location: filter.location } : {}),
    ...(filter.employmentType.length > 0 ? { employment_type: filter.employmentType } : {}),
    ...(filter.workType.length > 0 ? { work_type: filter.workType } : {}),
  }
}

function toApiModel(api: ApiSetting): ApiModel {
  return {
    enabled: api.isEnabled,
    locations: api.locations,
    country_wide: api.isCountryWide,
    delay_seconds: api.delaySeconds,
  }
}

function toSiteChangesModel(changes: SiteChanges): SiteChangesModel {
  const { isEnabled, maxAgeHours, filter, api, ...shared } = changes
  return {
    ...shared,
    ...(isEnabled === undefined ? {} : { enabled: isEnabled }),
    ...(maxAgeHours === undefined ? {} : { max_age_hours: maxAgeHours }),
    ...(filter === undefined ? {} : { filter: filter === null ? null : toFilterModel(filter) }),
    ...(api === undefined ? {} : { api: api === null ? null : toApiModel(api) }),
  }
}

export function toConfigChangesModel(changes: ConfigChanges): ConfigChangesModel {
  const { maxAgeHours, filter, defaultFields, sites, ...shared } = changes
  return {
    ...shared,
    ...(maxAgeHours === undefined ? {} : { max_age_hours: maxAgeHours }),
    ...(filter === undefined ? {} : { filter: toFilterModel(filter) }),
    ...(defaultFields === undefined ? {} : { default_fields: defaultFields }),
    ...(sites === undefined
      ? {}
      : {
          sites: Object.fromEntries(
            Object.entries(sites).map(([name, site]) => [name, toSiteChangesModel(site)]),
          ),
        }),
  }
}
