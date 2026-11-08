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

  describe('payloads', () => {
    const PAYLOAD = {
      keyword: 'AI Engineering',
      site: 'jobstreet',
      raw: { items: [1] },
      filtered: { count: 1, jobs: [{ title: 'Engineer' }] },
    }

    it('maps payloads with raw and filtered data', () => {
      const detail = toRunDetail({ ...MODEL, payloads: [PAYLOAD] })

      expect(detail.payloads).toEqual([PAYLOAD])
    })

    it('keeps null raw and filtered', () => {
      const detail = toRunDetail({
        ...MODEL,
        payloads: [{ ...PAYLOAD, raw: null, filtered: null }],
      })

      expect(detail.payloads).toEqual([{ ...PAYLOAD, raw: null, filtered: null }])
    })

    it('treats a missing payloads key as an empty list', () => {
      expect(toRunDetail(MODEL).payloads).toEqual([])
    })

    it('treats a payloads value that is not a list as an empty list', () => {
      const detail = toRunDetail({ ...MODEL, payloads: 'nope' as unknown as undefined })

      expect(detail.payloads).toEqual([])
    })

    it.each<[string, unknown]>([
      ['null', null],
      ['a string', 'text'],
      ['a number', 7],
      ['a list', [PAYLOAD]],
      ['a missing keyword', { site: 'jobstreet', raw: null, filtered: null }],
      ['a missing site', { keyword: 'AI', raw: null, filtered: null }],
      ['a keyword that is not text', { ...PAYLOAD, keyword: 4 }],
      ['a site that is not text', { ...PAYLOAD, site: null }],
      ['raw that is a list', { ...PAYLOAD, raw: [1, 2] }],
      ['raw that is text', { ...PAYLOAD, raw: 'text' }],
      ['filtered that is a number', { ...PAYLOAD, filtered: 5 }],
      ['filtered that is a list', { ...PAYLOAD, filtered: [] }],
      ['a missing raw key', { keyword: 'AI', site: 'jobstreet', filtered: null }],
    ])('drops an entry with %s', (_label, entry) => {
      const detail = toRunDetail({
        ...MODEL,
        payloads: [entry, PAYLOAD] as unknown as RunDetailModel['payloads'],
      })

      expect(detail.payloads).toEqual([PAYLOAD])
    })
  })
})
