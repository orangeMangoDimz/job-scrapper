import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { RunRecord, RunStatus } from '@/modules/runs/domain/entities/Run'
import RunHistory from '@/modules/runs/presentation/components/RunHistory.vue'

function makeRun(id: string, status: RunStatus, overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    id,
    status,
    keywords: ['python', 'vue'],
    sites: ['linkedin', 'indeed'],
    startedAt: '2026-11-07T08:30:00Z',
    finishedAt: null,
    jobCount: 12,
    errorCount: 0,
    error: null,
    ...overrides,
  }
}

function mountHistory(runs: RunRecord[], selectedId: string | null = null) {
  return mount(RunHistory, { props: { runs, selectedId } })
}

describe('RunHistory', () => {
  it('shows an empty state with a next step when there are no runs', () => {
    const wrapper = mountHistory([])

    const empty = wrapper.get('[data-slot="empty-state"]')
    expect(empty.text()).toContain('No runs yet.')
    expect(empty.text()).toContain('Start a scrape above')
    expect(wrapper.find('ul').exists()).toBe(false)
  })

  it('shows keywords, sites and job count on each row', () => {
    const wrapper = mountHistory([makeRun('a', 'succeeded')])
    const row = wrapper.get('li button')

    expect(row.text()).toContain('python, vue')
    expect(row.text()).toContain('linkedin, indeed')
    expect(row.text()).toContain('12 jobs')
  })

  it('says 1 job, not 1 jobs', () => {
    const wrapper = mountHistory([makeRun('a', 'succeeded', { jobCount: 1 })])

    expect(wrapper.get('li button').text()).toContain('1 job')
    expect(wrapper.get('li button').text()).not.toContain('1 jobs')
  })

  it.each<[RunStatus, string, string]>([
    ['running', 'Running', 'neutral'],
    ['succeeded', 'Succeeded', 'accent'],
    ['partial', 'Partial', 'neutral'],
    ['failed', 'Failed', 'danger'],
    ['interrupted', 'Interrupted', 'danger'],
  ])('labels a %s run as %s with the %s tone', (status, label, tone) => {
    const wrapper = mountHistory([makeRun('a', status)])
    const badge = wrapper.get('[data-slot="badge"]')

    expect(badge.text()).toBe(label)
    expect(badge.attributes('data-tone')).toBe(tone)
  })

  it('marks only the selected run as current', () => {
    const wrapper = mountHistory([makeRun('a', 'succeeded'), makeRun('b', 'failed')], 'b')
    const rows = wrapper.findAll('li button')

    expect(rows[0]!.attributes('aria-current')).toBeUndefined()
    expect(rows[1]!.attributes('aria-current')).toBe('true')
  })

  it('emits select with the run id when a row is clicked', async () => {
    const wrapper = mountHistory([makeRun('a', 'succeeded'), makeRun('b', 'failed')])

    await wrapper.findAll('li button')[1]!.trigger('click')

    expect(wrapper.emitted('select')).toEqual([['b']])
  })
})
