import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import type { SiteSetting } from '@/modules/config/domain/entities/ScraperConfig'
import SiteSettings from '@/modules/config/presentation/components/SiteSettings.vue'

const SITE: SiteSetting = {
  name: 'glints',
  isEnabled: true,
  limit: 3,
  maxAgeHours: null,
  filter: null,
  fields: null,
  api: null,
}

function mountSite(site: SiteSetting) {
  return mount(SiteSettings, {
    props: {
      site,
      defaultFields: ['salary_min'],
      jobFields: ['site', 'title', 'salary_min', 'company_id'],
      mandatoryFields: ['site', 'title'],
    },
    attachTo: document.body,
  })
}

function lastUpdate(wrapper: ReturnType<typeof mountSite>): SiteSetting | undefined {
  const updates = wrapper.emitted('update') ?? []
  return updates[updates.length - 1]?.[0] as SiteSetting | undefined
}

describe('SiteSettings job fields', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('hides the field grid while the site uses the default job fields', () => {
    const wrapper = mountSite(SITE)

    expect(wrapper.find('#glints-field-salary_min').exists()).toBe(false)
  })

  it('starts its own job fields from the default ones', async () => {
    const wrapper = mountSite(SITE)

    await wrapper.get('#glints-own-fields').trigger('click')
    await flushPromises()

    expect(lastUpdate(wrapper)?.fields).toEqual(['salary_min'])
  })

  it('shows its own job fields as checkboxes with the always-saved ones locked', () => {
    const wrapper = mountSite({ ...SITE, fields: ['company_id'] })

    expect(wrapper.get('#glints-field-site').attributes('disabled')).toBeDefined()
    expect(wrapper.get('#glints-field-company_id').attributes('data-state')).toBe('checked')
    expect(wrapper.get('#glints-field-salary_min').attributes('data-state')).toBe('unchecked')
  })

  it('saves an emptied pick as an empty list, not as the default fields', async () => {
    const wrapper = mountSite({ ...SITE, fields: ['company_id'] })

    await wrapper.get('#glints-field-company_id').trigger('click')
    await flushPromises()

    expect(lastUpdate(wrapper)?.fields).toEqual([])
  })
})
