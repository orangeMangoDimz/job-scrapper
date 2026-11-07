import { describe, expect, it } from 'vitest'
import {
  EMPTY_FILTER,
  hasConfigChanges,
  toConfigChanges,
  toDelaySeconds,
  toJobFieldLabel,
  toOptionalNumber,
  type ConfigValues,
  type SiteSetting,
} from '@/modules/config/domain/entities/ScraperConfig'

const SITE: SiteSetting = {
  name: 'upwork',
  isEnabled: true,
  limit: 30,
  maxAgeHours: null,
  filter: EMPTY_FILTER,
  fields: null,
  api: { isEnabled: true, locations: ['Remote'], isCountryWide: false, delaySeconds: null },
}

const ORIGINAL: ConfigValues = {
  keywords: ['django'],
  limit: 3,
  maxAgeHours: 72,
  filter: { ...EMPTY_FILTER, location: ['jakarta'] },
  defaultFields: ['title'],
  sites: [SITE],
}

function withSite(changes: Partial<SiteSetting>): ConfigValues {
  return { ...ORIGINAL, sites: [{ ...SITE, ...changes }] }
}

describe('toConfigChanges', () => {
  it('sends nothing when nothing changed', () => {
    expect(hasConfigChanges(toConfigChanges(ORIGINAL, ORIGINAL))).toBe(false)
  })

  it('sends only the changed field', () => {
    expect(toConfigChanges({ ...ORIGINAL, limit: 9 }, ORIGINAL)).toEqual({ limit: 9 })
  })

  it('sends a changed filter whole', () => {
    const filter = { ...EMPTY_FILTER, workType: ['remote'] }

    expect(toConfigChanges({ ...ORIGINAL, filter }, ORIGINAL)).toEqual({ filter })
  })

  it('sends changed default fields', () => {
    const changes = toConfigChanges({ ...ORIGINAL, defaultFields: ['title', 'url'] }, ORIGINAL)

    expect(changes).toEqual({ defaultFields: ['title', 'url'] })
  })

  it('sends only the changed site field', () => {
    expect(toConfigChanges(withSite({ isEnabled: false }), ORIGINAL)).toEqual({
      sites: { upwork: { isEnabled: false } },
    })
  })

  it('sends null when a site goes back to the global value', () => {
    expect(toConfigChanges(withSite({ limit: null, filter: null }), ORIGINAL)).toEqual({
      sites: { upwork: { limit: null, filter: null } },
    })
  })

  it('sends a changed api block whole', () => {
    const api = { ...SITE.api!, delaySeconds: [4, 6] as [number, number] }

    expect(toConfigChanges(withSite({ api }), ORIGINAL)).toEqual({
      sites: { upwork: { api } },
    })
  })

  it('leaves out emptied global numbers', () => {
    expect(toConfigChanges({ ...ORIGINAL, limit: null, maxAgeHours: null }, ORIGINAL)).toEqual({})
  })
})

describe('toOptionalNumber', () => {
  it('turns input text into a number', () => {
    expect(toOptionalNumber('12')).toBe(12)
  })

  it('turns empty input into null', () => {
    expect(toOptionalNumber('')).toBeNull()
  })
})

describe('toDelaySeconds', () => {
  it('keeps both values', () => {
    expect(toDelaySeconds(4, 6)).toEqual([4, 6])
  })

  it('turns two empty values into null', () => {
    expect(toDelaySeconds(null, null)).toBeNull()
  })

  it('fills a missing value from the other one', () => {
    expect(toDelaySeconds(4, null)).toEqual([4, 4])
    expect(toDelaySeconds(null, 6)).toEqual([6, 6])
  })
})

describe('toJobFieldLabel', () => {
  it.each([
    ['salary_min', 'Salary min'],
    ['company_id', 'Company ID'],
    ['job_id', 'Job ID'],
    ['matched_keyword', 'Matched keyword'],
    ['url', 'URL'],
    ['title', 'Title'],
  ])('turns %s into %s', (field, label) => {
    expect(toJobFieldLabel(field)).toBe(label)
  })
})
