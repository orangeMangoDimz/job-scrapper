import { describe, expect, it } from 'vitest'
import { toRunDetail, type RunDetailModel } from '@/modules/runs/data/models/RunModel'

const MODEL: RunDetailModel = {
  record: {
    id: 'run-1',
    status: 'partial',
    keywords: ['django'],
    sites: ['upwork'],
    started_at: '2026-11-01T10:00:00+00:00',
    finished_at: '2026-11-01T10:01:00+00:00',
    job_count: 1,
    error_count: 1,
    error: null,
  },
  jobs: [
    {
      site: 'upwork',
      matched_keyword: 'django',
      title: 'Engineer',
      company: 'Upwork Client',
      location: 'Remote',
      url: 'https://www.upwork.com/jobs/1',
      posted_at: '2026-11-01T09:00:00+00:00',
    },
  ],
  failures: [{ keyword: 'django', site: 'indeed', reason: 'timeout' }],
}

describe('toRunDetail', () => {
  it('maps API fields', () => {
    const detail = toRunDetail(MODEL)

    expect(detail.record.jobCount).toBe(1)
    expect(detail.record.startedAt).toBe('2026-11-01T10:00:00+00:00')
    expect(detail.jobs[0]?.matchedKeyword).toBe('django')
    expect(detail.failures[0]?.reason).toBe('timeout')
  })

  it('keeps web links', () => {
    expect(toRunDetail(MODEL).jobs[0]?.url).toBe('https://www.upwork.com/jobs/1')
  })

  it('drops links that are not web links', () => {
    const detail = toRunDetail({ ...MODEL, jobs: [{ url: 'javascript:alert(1)' }] })

    expect(detail.jobs[0]?.url).toBeNull()
  })

  it('fills missing job fields with null', () => {
    const detail = toRunDetail({ ...MODEL, jobs: [{ title: 'Only title' }] })

    expect(detail.jobs[0]?.company).toBeNull()
  })
})
