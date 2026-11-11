import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import DiscordJobPicker from '@/modules/discord/presentation/components/DiscordJobPicker.vue'
import { Select } from '@/shared/components/ui/select'
import type { RunDetail, RunRecord } from '@/modules/runs/domain/entities/Run'

function makeRun(id: string, jobCount: number): RunRecord {
  return {
    id,
    status: 'succeeded',
    keywords: ['django', 'vue'],
    sites: ['upwork'],
    startedAt: '2026-11-01T10:00:00+00:00',
    finishedAt: null,
    jobCount,
    errorCount: 0,
    error: null,
  }
}

function makeDetail(jobCount: number): RunDetail {
  return {
    record: makeRun('r1', jobCount),
    jobs: Array.from({ length: jobCount }, (_, index) => ({
      site: 'upwork',
      matchedKeyword: 'django',
      title: index === 1 ? null : `Job ${index}`,
      company: 'Acme',
      location: 'Remote',
      url: null,
      postedAt: null,
    })),
    failures: [],
    payloads: [],
  }
}

interface Props {
  runs?: RunRecord[]
  detail?: RunDetail | null
  pickedIndexes?: number[]
  isLoading?: boolean
  error?: string | null
}

function mountPicker(props: Props = {}) {
  const detail = props.detail === undefined ? makeDetail(3) : props.detail
  return mount(DiscordJobPicker, {
    props: {
      runs: props.runs ?? [makeRun('r1', 3)],
      detail,
      pickedIndexes: props.pickedIndexes ?? detail?.jobs.map((_, index) => index) ?? [],
      isLoading: props.isLoading ?? false,
      error: props.error ?? null,
    },
  })
}

describe('DiscordJobPicker', () => {
  it('shows an empty state when no run found jobs', () => {
    const wrapper = mountPicker({ runs: [], detail: null })

    expect(wrapper.get('[data-slot="empty-state"]').text()).toContain('No runs with jobs yet.')
    expect(wrapper.find('#discord-run').exists()).toBe(false)
  })

  it('asks to pick a run before any is loaded', () => {
    const wrapper = mountPicker({ detail: null })

    expect(wrapper.find('#discord-run').exists()).toBe(true)
    expect(wrapper.find('ul').exists()).toBe(false)
    expect(wrapper.text()).toContain('Pick a run to see its jobs')
  })

  it('emits selectRun when a run is picked', () => {
    const wrapper = mountPicker({ detail: null })

    wrapper.getComponent(Select).vm.$emit('update:modelValue', 'r1')

    expect(wrapper.emitted('selectRun')).toEqual([['r1']])
  })

  it('shows a ticked checkbox for every picked job with its title and company', () => {
    const wrapper = mountPicker()
    const rows = wrapper.findAll('li')

    expect(rows).toHaveLength(3)
    expect(rows[0]!.text()).toContain('Job 0')
    expect(rows[0]!.text()).toContain('Acme')
    expect(wrapper.get('#discord-job-0').attributes('data-state')).toBe('checked')
  })

  it('calls an untitled job Untitled job', () => {
    const wrapper = mountPicker()

    expect(wrapper.findAll('li')[1]!.text()).toContain('Untitled job')
  })

  it('shows an unticked checkbox for a job that is not picked', () => {
    const wrapper = mountPicker({ pickedIndexes: [0, 2] })

    expect(wrapper.get('#discord-job-1').attributes('data-state')).toBe('unchecked')
  })

  it('emits pick with the index when a checkbox is clicked', async () => {
    const wrapper = mountPicker()

    await wrapper.get('#discord-job-1').trigger('click')

    expect(wrapper.emitted('pick')).toEqual([[1, false]])
  })

  it('counts the ticked jobs', () => {
    const wrapper = mountPicker({ pickedIndexes: [0, 2] })

    expect(wrapper.text()).toContain('2 of 3 jobs picked')
  })

  it('emits clear while some are ticked and pickAll when none are', async () => {
    const some = mountPicker()
    await some.get('[data-slot="toggle-all"]').trigger('click')
    expect(some.emitted('clear')).toHaveLength(1)

    const none = mountPicker({ pickedIndexes: [] })
    await none.get('[data-slot="toggle-all"]').trigger('click')
    expect(none.emitted('pickAll')).toHaveLength(1)
  })

  it('explains the 50 job limit when more are ticked', () => {
    const wrapper = mountPicker({
      detail: makeDetail(60),
      pickedIndexes: Array.from({ length: 51 }, (_, index) => index),
    })

    expect(wrapper.get('[role="alert"]').text()).toContain('Discord takes at most 50 jobs per send')
    expect(wrapper.get('[role="alert"]').text()).toContain('51')
  })

  it('shows no limit message at exactly 50 jobs', () => {
    const wrapper = mountPicker({
      detail: makeDetail(60),
      pickedIndexes: Array.from({ length: 50 }, (_, index) => index),
    })

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('shows the error when the run fails to load', () => {
    const wrapper = mountPicker({ detail: null, error: 'Run gone' })

    expect(wrapper.get('[role="alert"]').text()).toContain('Run gone')
  })

  it('shows a loading status while the run loads', () => {
    const wrapper = mountPicker({ detail: null, isLoading: true })

    expect(wrapper.get('[role="status"]').text()).toContain('Loading jobs')
  })
})
