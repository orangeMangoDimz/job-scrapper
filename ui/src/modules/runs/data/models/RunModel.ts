import type {
  JsonObject,
  RunDetail,
  RunJob,
  RunPayload,
  RunOptions,
  RunRecord,
  RunStatus,
} from '@/modules/runs/domain/entities/Run'

export interface RunRecordModel {
  id: string
  status: RunStatus
  keywords: string[]
  sites: string[]
  started_at: string
  finished_at: string | null
  job_count: number
  error_count: number
  error: string | null
}

export interface RunJobModel {
  site?: string | null
  matched_keyword?: string | null
  title?: string | null
  company?: string | null
  location?: string | null
  url?: string | null
  posted_at?: string | null
}

export interface RunDetailModel {
  record: RunRecordModel
  jobs: RunJobModel[]
  failures: RunDetail['failures']
  payloads?: unknown[]
}

export interface RunOptionsModel {
  keywords: string[]
  sites: { name: string; enabled: boolean }[]
  is_stale: boolean
}

const WEB_URL = /^https?:\/\//i

function toWebUrl(url: string | null | undefined): string | null {
  return url != null && WEB_URL.test(url) ? url : null
}

export function toRunRecord(model: RunRecordModel): RunRecord {
  return {
    id: model.id,
    status: model.status,
    keywords: model.keywords,
    sites: model.sites,
    startedAt: model.started_at,
    finishedAt: model.finished_at,
    jobCount: model.job_count,
    errorCount: model.error_count,
    error: model.error,
  }
}

function toRunJob(model: RunJobModel): RunJob {
  return {
    site: model.site ?? null,
    matchedKeyword: model.matched_keyword ?? null,
    title: model.title ?? null,
    company: model.company ?? null,
    location: model.location ?? null,
    url: toWebUrl(model.url),
    postedAt: model.posted_at ?? null,
  }
}

function isPlainObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isObjectOrNull(value: unknown): value is JsonObject | null {
  return value === null || isPlainObject(value)
}

function toRunPayload(entry: unknown): RunPayload | null {
  if (!isPlainObject(entry)) {
    return null
  }
  const { keyword, site, raw, filtered } = entry
  if (typeof keyword !== 'string' || typeof site !== 'string') {
    return null
  }
  if (!isObjectOrNull(raw) || !isObjectOrNull(filtered)) {
    return null
  }
  return { keyword, site, raw, filtered }
}

function toRunPayloads(entries: unknown): RunPayload[] {
  if (!Array.isArray(entries)) {
    return []
  }
  return entries.flatMap((entry) => {
    const payload = toRunPayload(entry)
    return payload === null ? [] : [payload]
  })
}

export function toRunDetail(model: RunDetailModel): RunDetail {
  return {
    record: toRunRecord(model.record),
    jobs: model.jobs.map(toRunJob),
    failures: model.failures,
    payloads: toRunPayloads(model.payloads),
  }
}

export function toRunOptions(model: RunOptionsModel): RunOptions {
  return {
    keywords: model.keywords,
    sites: model.sites.map((site) => ({ name: site.name, isEnabled: site.enabled })),
    isStale: model.is_stale,
  }
}
