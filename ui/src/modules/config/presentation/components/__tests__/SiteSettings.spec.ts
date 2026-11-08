import { afterEach, describe, expect, it, vi } from 'vitest'
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

const API_SITE: SiteSetting = {
  ...SITE,
  api: { isEnabled: true, locations: [], isCountryWide: false, delaySeconds: null },
}

const LOCATION_OPTIONS = [
  { label: 'Jakarta', value: '78d63064-78a1-4577-8516-036a6c5e903e' },
  { label: 'Bandung', value: 'bandung-id' },
]

const EMPTY_WARNING = 'No city and no country search: this site finds nothing'

function mountApiSite(site: SiteSetting, locationOptions?: typeof LOCATION_OPTIONS) {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn<ResizeObserver['observe']>()
      unobserve = vi.fn<ResizeObserver['unobserve']>()
      disconnect = vi.fn<ResizeObserver['disconnect']>()
    },
  )
  return mount(SiteSettings, {
    props: {
      site,
      defaultFields: [],
      jobFields: [],
      mandatoryFields: [],
      locationOptions,
    },
    attachTo: document.body,
  })
}

describe('SiteSettings API locations', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('shows no locations box when the site has no city list', () => {
    const wrapper = mountApiSite({ ...API_SITE, api: { ...API_SITE.api!, locations: ['Remote'] } })

    expect(wrapper.find('#glints-api-locations').exists()).toBe(false)
    expect(wrapper.text()).not.toContain(EMPTY_WARNING)
  })

  it('shows no locations box when the city list is empty', () => {
    const wrapper = mountApiSite({ ...API_SITE, api: { ...API_SITE.api!, locations: [] } }, [])

    expect(wrapper.find('#glints-api-locations').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('API locations')
    expect(wrapper.text()).not.toContain(EMPTY_WARNING)
  })

  it('shows the city picker with chips for the saved values', () => {
    const wrapper = mountApiSite(
      { ...API_SITE, api: { ...API_SITE.api!, locations: [LOCATION_OPTIONS[0]!.value] } },
      LOCATION_OPTIONS,
    )

    expect(wrapper.find('#glints-api-locations').exists()).toBe(true)
    expect(wrapper.text()).toContain('API locations')
    expect(wrapper.text()).not.toContain('one per line')
    expect(wrapper.text()).toContain('Jakarta')
  })

  it('warns when no city is picked and the whole country is off', () => {
    const wrapper = mountApiSite(API_SITE, LOCATION_OPTIONS)

    expect(wrapper.text()).toContain(EMPTY_WARNING)
  })

  it('does not warn when the whole country is searched', () => {
    const wrapper = mountApiSite(
      { ...API_SITE, api: { ...API_SITE.api!, isCountryWide: true } },
      LOCATION_OPTIONS,
    )

    expect(wrapper.text()).not.toContain(EMPTY_WARNING)
  })

  it('does not warn when a city is picked', () => {
    const wrapper = mountApiSite(
      { ...API_SITE, api: { ...API_SITE.api!, locations: ['bandung-id'] } },
      LOCATION_OPTIONS,
    )

    expect(wrapper.text()).not.toContain(EMPTY_WARNING)
  })

  it('gives each empty text and number box a placeholder', () => {
    const wrapper = mountApiSite(
      { ...API_SITE, filter: { location: [], employmentType: [], workType: [] } },
      LOCATION_OPTIONS,
    )

    expect(wrapper.get('#glints-api-delay-min').attributes('placeholder')).toBe('Min delay')
    expect(wrapper.get('[aria-label="glints max delay"]').attributes('placeholder')).toBe(
      'Max delay',
    )
    expect(wrapper.get('#glints-max-age').attributes('placeholder')).toBe('Global')
    expect(wrapper.get('#glints-location').attributes('placeholder')).toBe('Locations')
    expect(wrapper.get('#glints-employment').attributes('placeholder')).toBe('Employment types')
    expect(wrapper.get('#glints-work').attributes('placeholder')).toBe('Work types')
  })
})
