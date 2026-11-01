import { describe, expect, it } from 'vitest'
import { toConfigChangesModel } from '@/modules/config/data/models/ConfigModel'

describe('toConfigChangesModel', () => {
  it('maps changed fields to API names', () => {
    const model = toConfigChangesModel({
      maxAgeHours: 24,
      proxyUrl: null,
      sites: { upwork: { isEnabled: false } },
    })

    expect(model).toEqual({
      max_age_hours: 24,
      proxy_url: null,
      sites: { upwork: { enabled: false } },
    })
  })

  it('leaves out fields that did not change', () => {
    expect(toConfigChangesModel({ limit: 9 })).toEqual({ limit: 9 })
  })
})
