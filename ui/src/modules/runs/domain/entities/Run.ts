export type RunStatus = 'running' | 'succeeded' | 'partial' | 'failed' | 'interrupted'

export interface RunRecord {
  id: string
  status: RunStatus
  keywords: string[]
  sites: string[]
  startedAt: string
  finishedAt: string | null
  jobCount: number
  errorCount: number
  error: string | null
}

export interface RunJob {
  site: string | null
  matchedKeyword: string | null
  title: string | null
  company: string | null
  location: string | null
  url: string | null
  postedAt: string | null
}

export interface RunFailure {
  keyword: string
  site: string
  reason: string
}

export interface RunDetail {
  record: RunRecord
  jobs: RunJob[]
  failures: RunFailure[]
}

export interface SiteOption {
  name: string
  isEnabled: boolean
}

export interface RunOptions {
  keywords: string[]
  sites: SiteOption[]
  isStale: boolean
}
