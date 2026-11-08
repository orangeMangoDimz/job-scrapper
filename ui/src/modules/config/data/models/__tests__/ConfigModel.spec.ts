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
  job_fields: ['site', 'title', 'location', 'salary_min'],
  mandatory_fields: ['site'],
}

describe('toConfigSnapshot', () => {
  it('maps API names and fills filter lists', () => {
    const snapshot = toConfigSnapshot(MODEL)

    expect(snapshot.version).toBe(4)
    expect(snapshot.updatedBy).toBe('ui')
    expect(snapshot.values.filter).toEqual({
      location: ['jakarta'],
      employmentType: [],
      workType: [],
    })
    expect(snapshot.values.defaultFields).toEqual(['title'])
  })

  it('lists the job fields and the always-saved ones', () => {
    const snapshot = toConfigSnapshot(MODEL)

    expect(snapshot.jobFields).toEqual(['site', 'title', 'location', 'salary_min'])
    expect(snapshot.mandatoryFields).toEqual(['site'])
  })

  it('drops unknown and always-saved names from the picked job fields', () => {
    const [upwork] = MODEL.values.sites
    const model: ConfigModel = {
      ...MODEL,
      values: {
        ...MODEL.values,
        default_fields: ['site', 'salary_min', 'old_field', 'title'],
        sites: [{ ...upwork!, fields: ['old_field', 'site', 'location'] }],
      },
    }

    const { values } = toConfigSnapshot(model)

    expect(values.defaultFields).toEqual(['salary_min', 'title'])
    expect(values.sites[0]?.fields).toEqual(['location'])
  })

  it('keeps a site that uses the default job fields at null', () => {
    const [upwork] = toConfigSnapshot(MODEL).values.sites

    expect(upwork?.fields).toBeNull()
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

describe('toConfigSnapshot location options', () => {
  it('maps the city list of each site', () => {
    const model: ConfigModel = {
      ...MODEL,
      location_options: {
        glints: [
          { label: 'Jakarta', value: '78d63064' },
          { label: 'Bandung', value: 'bandung-id' },
        ],
      },
    }

    expect(toConfigSnapshot(model).locationOptions).toEqual({
      glints: [
        { label: 'Jakarta', value: '78d63064' },
        { label: 'Bandung', value: 'bandung-id' },
      ],
    })
  })

  it('treats a missing location_options key as no lists', () => {
    expect(toConfigSnapshot(MODEL).locationOptions).toEqual({})
  })

  it('skips a malformed list and malformed entries', () => {
    const model = {
      ...MODEL,
      location_options: {
        glints: [
          { label: 'Jakarta', value: 'ok' },
          { label: 5, value: 'x' },
          null,
          { label: 'No value' },
        ],
        jobstreet: 'oops',
        linkedin: null,
      },
    } as unknown as ConfigModel

    expect(toConfigSnapshot(model).locationOptions).toEqual({
      glints: [{ label: 'Jakarta', value: 'ok' }],
    })
  })

  it('treats a location_options that is not an object as no lists', () => {
    const model = { ...MODEL, location_options: [] } as unknown as ConfigModel

    expect(toConfigSnapshot(model).locationOptions).toEqual({})
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
          api: {
            isEnabled: true,
            locations: ['Remote'],
            isCountryWide: true,
            delaySeconds: [4, 6],
          },
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
