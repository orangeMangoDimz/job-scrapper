import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import type { RunPayload } from '@/modules/runs/domain/entities/Run'
import RunJsonPanel from '@/modules/runs/presentation/components/RunJsonPanel.vue'

function payload(filtered: RunPayload['filtered']): RunPayload {
  return { keyword: 'Vue', site: 'indeed', raw: filtered, filtered }
}

function mountPanel(filtered: RunPayload['filtered'], field: 'raw' | 'filtered' = 'filtered') {
  return mount(RunJsonPanel, {
    props: { payloads: [payload(filtered)], pickedIndex: 0, field },
    attachTo: document.body,
  })
}

describe('RunJsonPanel job count', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('shows the count field as the job count', () => {
    const wrapper = mountPanel({ count: 12, jobs: [{}] })

    expect(wrapper.get('[data-slot="json-count"]').text()).toBe('12 jobs')
  })

  it('falls back to the jobs length when there is no count', () => {
    const wrapper = mountPanel({ jobs: [{}, {}] })

    expect(wrapper.get('[data-slot="json-count"]').text()).toBe('2 jobs')
  })

  it('ignores a count that is not a number', () => {
    const wrapper = mountPanel({ count: 'many', jobs: [{}, {}, {}] })

    expect(wrapper.get('[data-slot="json-count"]').text()).toBe('3 jobs')
  })

  it('shows no count when the file has neither count nor jobs', () => {
    const wrapper = mountPanel({ items: [1, 2] })

    expect(wrapper.find('[data-slot="json-count"]').exists()).toBe(false)
  })

  it('shows no count for a count that is not finite', () => {
    const wrapper = mountPanel({ count: null })

    expect(wrapper.find('[data-slot="json-count"]').exists()).toBe(false)
  })
})
