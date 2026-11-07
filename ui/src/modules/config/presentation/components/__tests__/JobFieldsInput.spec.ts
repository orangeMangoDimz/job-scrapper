import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import JobFieldsInput from '@/modules/config/presentation/components/JobFieldsInput.vue'

const JOB_FIELDS = ['site', 'title', 'company_id', 'salary_min', 'salary_max']
const MANDATORY_FIELDS = ['site', 'title']

function mountInput(modelValue: string[], jobFields: string[] = JOB_FIELDS) {
  return mount(JobFieldsInput, {
    props: {
      idPrefix: 'global',
      legend: 'Job fields',
      modelValue,
      jobFields,
      mandatoryFields: MANDATORY_FIELDS,
    },
    attachTo: document.body,
  })
}

function checkbox(wrapper: ReturnType<typeof mountInput>, label: string) {
  const id = wrapper
    .findAll('label')
    .find((node) => node.text() === label)!
    .attributes('for')
  return wrapper.get(`#${id}`)
}

describe('JobFieldsInput', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('lists every job field with a readable label in the scraper order', () => {
    const wrapper = mountInput([])

    expect(wrapper.findAll('label').map((label) => label.text())).toEqual([
      'Site',
      'Title',
      'Company ID',
      'Salary min',
      'Salary max',
    ])
  })

  it('shows always-saved fields ticked and locked', () => {
    const wrapper = mountInput([])
    const site = checkbox(wrapper, 'Site')

    expect(site.attributes('data-state')).toBe('checked')
    expect(site.attributes('disabled')).toBeDefined()
    expect(checkbox(wrapper, 'Salary min').attributes('disabled')).toBeUndefined()
  })

  it('ticks the picked optional fields', () => {
    const wrapper = mountInput(['salary_max'])

    expect(checkbox(wrapper, 'Salary max').attributes('data-state')).toBe('checked')
    expect(checkbox(wrapper, 'Company ID').attributes('data-state')).toBe('unchecked')
  })

  it('emits the optional fields in the scraper order when one is ticked', async () => {
    const wrapper = mountInput(['salary_max'])

    await checkbox(wrapper, 'Company ID').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')).toEqual([[['company_id', 'salary_max']]])
  })

  it('emits the list without a field when it is unticked', async () => {
    const wrapper = mountInput(['company_id', 'salary_max'])

    await checkbox(wrapper, 'Salary max').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')).toEqual([[['company_id']]])
  })

  it('says the field list is missing instead of showing an empty grid', () => {
    const wrapper = mountInput(['salary_max'], [])

    expect(wrapper.find('[data-slot="checkbox"]').exists()).toBe(false)
    expect(wrapper.get('[data-slot="empty-state"]').text()).toContain('No job field list')
  })
})
