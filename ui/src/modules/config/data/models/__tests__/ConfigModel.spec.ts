import { describe, expect, it } from 'vitest'
import {
  toConfigChangesModel,
  toConfigSnapshot,
  toConfigVersions,
  type ConfigModel,
} from '@/modules/config/data/models/ConfigModel'

const MODEL: ConfigModel = {
  values: {
    keywords: ['django'],
    limit: 3,
    max_age_hours: 72,
    filter: { location: ['jakarta'] },
    default_fields: ['title'],
    sites: [
      {
        name: 'upwork',
        enabled: true,
        limit: 30,
        max_age_hours: null,
        filter: {},
        fields: null,
        api: { locations: ['Remote'] },
      },
      {
        name: 'indeed',
        enabled: false,
        limit: null,
        max_age_hours: 24,
        filter: null,
        fields: ['title'],
        api: null,
      },
    ],
  },
  version: 4,
  updated_at: '2026-11-02T01:00:00+00:00',
  updated_by: 'ui',
  is_stale: false,
}

describe('toConfigSnapshot', () => {
  it('maps API names and fills filter lists', () => {
    const snapshot = toConfigSnapshot(MODEL)

    expect(snapshot.version).toBe(4)
    expect(snapshot.updatedBy).toBe('ui')
    expect(snapshot.values.filter).toEqual({ location: ['jakarta'], employmentType: [], workType: [] })
    expect(snapshot.values.defaultFields).toEqual(['title'])
  })

  it('keeps no filter apart from the global filter', () => {
    const [upwork, indeed] = toConfigSnapshot(MODEL).values.sites

    expect(upwork?.filter).toEqual({ location: [], employmentType: [], workType: [] })
    expect(indeed?.filter).toBeNull()
  })

  it('fills api defaults', () => {
    const [upwork, indeed] = toConfigSnapshot(MODEL).values.sites

    expect(upwork?.api).toEqual({
      isEnabled: true,
      locations: ['Remote'],
      isCountryWide: false,
      delaySeconds: null,
    })
    expect(indeed?.api).toBeNull()
  })
})

describe('toConfigChangesModel', () => {
  it('maps changed fields to API names', () => {
    const model = toConfigChangesModel({
      maxAgeHours: 24,
      defaultFields: ['title'],
      sites: {
        upwork: {
          isEnabled: false,
          maxAgeHours: null,
          filter: { location: [], employmentType: ['contract'], workType: [] },
          api: { isEnabled: true, locations: ['Remote'], isCountryWide: true, delaySeconds: [4, 6] },
        },
      },
    })

    expect(model).toEqual({
      max_age_hours: 24,
      default_fields: ['title'],
      sites: {
        upwork: {
          enabled: false,
          max_age_hours: null,
          filter: { employment_type: ['contract'] },
          api: { enabled: true, locations: ['Remote'], country_wide: true, delay_seconds: [4, 6] },
        },
      },
    })
  })

  it('keeps null for a site that goes back to the global filter', () => {
    expect(toConfigChangesModel({ sites: { upwork: { filter: null } } })).toEqual({
      sites: { upwork: { filter: null } },
    })
  })

  it('sends an empty filter for no filter', () => {
    const filter = { location: [], employmentType: [], workType: [] }

    expect(toConfigChangesModel({ sites: { upwork: { filter } } })).toEqual({
      sites: { upwork: { filter: {} } },
    })
  })

  it('leaves out fields that did not change', () => {
    expect(toConfigChangesModel({ limit: 9 })).toEqual({ limit: 9 })
  })
})

describe('toConfigVersions', () => {
  it('maps history entries', () => {
    const versions = toConfigVersions({
      entries: [
        {
          version: 3,
          updated_at: '2026-11-01T01:00:00+00:00',
          updated_by: 'seed',
          keywords: ['django'],
          enabled_sites: ['upwork'],
        },
      ],
    })

    expect(versions).toEqual([
      {
        version: 3,
        updatedAt: '2026-11-01T01:00:00+00:00',
        updatedBy: 'seed',
        keywords: ['django'],
        enabledSites: ['upwork'],
      },
    ])
  })
})
