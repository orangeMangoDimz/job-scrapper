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
    discordStatus: null,
    discordSent: 0,
    discordFailed: 0,
    discordError: null,
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

  it('shows only the first 3 runs and no toggle when there are 3 or fewer', () => {
    const wrapper = mountHistory(['a', 'b', 'c'].map((id) => makeRun(id, 'succeeded')))

    expect(wrapper.findAll('li')).toHaveLength(3)
    expect(wrapper.find('[aria-controls]').exists()).toBe(false)
  })

  it('collapses to the first 3 runs and expands and collapses with the toggle', async () => {
    const wrapper = mountHistory(['a', 'b', 'c', 'd', 'e'].map((id) => makeRun(id, 'succeeded')))
    const toggle = wrapper.get('[aria-controls]')

    expect(wrapper.findAll('li')).toHaveLength(3)
    expect(toggle.text()).toContain('Show 2 more')
    expect(toggle.attributes('aria-expanded')).toBe('false')

    await toggle.trigger('click')

    expect(wrapper.findAll('li')).toHaveLength(5)
    expect(toggle.text()).toContain('Show less')
    expect(toggle.attributes('aria-expanded')).toBe('true')

    await toggle.trigger('click')

    expect(wrapper.findAll('li')).toHaveLength(3)
  })

  it('keeps the selected run on screen when the list is collapsed', () => {
    const runs = ['a', 'b', 'c', 'd', 'e'].map((id) => makeRun(id, 'succeeded'))
    const wrapper = mountHistory(runs, 'e')
    const rows = wrapper.findAll('li button')

    expect(rows).toHaveLength(4)
    expect(rows[3]!.attributes('aria-current')).toBe('true')
    expect(wrapper.get('[aria-controls]').text()).toContain('Show 1 more')
  })

  it('points the toggle at the list it controls', () => {
    const wrapper = mountHistory(['a', 'b', 'c', 'd'].map((id) => makeRun(id, 'succeeded')))
    const listId = wrapper.get('ul').attributes('id')

    expect(listId).toBeTruthy()
    expect(wrapper.get('[aria-controls]').attributes('aria-controls')).toBe(listId)
  })

  describe('discord status', () => {
    it('shows nothing about Discord when there was no send', () => {
      const wrapper = mountHistory([makeRun('a', 'succeeded')])

      expect(wrapper.get('li button').text()).not.toContain('Discord')
    })

    it('shows that it is sending', () => {
      const wrapper = mountHistory([makeRun('a', 'succeeded', { discordStatus: 'sending' })])

      expect(wrapper.get('li button').text()).toContain('Sending to Discord')
      expect(wrapper.get('[data-slot="discord-status"]').attributes('data-tone')).toBe('neutral')
    })

    it('shows how many were sent', () => {
      const wrapper = mountHistory([
        makeRun('a', 'succeeded', { discordStatus: 'sent', discordSent: 7 }),
      ])

      expect(wrapper.get('li button').text()).toContain('Sent 7 to Discord')
    })

    it('shows how many were sent and failed', () => {
      const wrapper = mountHistory([
        makeRun('a', 'succeeded', { discordStatus: 'partial', discordSent: 5, discordFailed: 2 }),
      ])

      expect(wrapper.get('li button').text()).toContain('Sent 5, failed 2 on Discord')
    })

    it('shows the reason when Discord failed in the danger tone', () => {
      const wrapper = mountHistory([
        makeRun('a', 'succeeded', { discordStatus: 'failed', discordError: 'Missing access' }),
      ])
      const badge = wrapper.get('[data-slot="discord-status"]')

      expect(badge.text()).toBe('Discord failed: Missing access')
      expect(badge.attributes('data-tone')).toBe('danger')
    })
  })
})
