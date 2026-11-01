import { describe, expect, it } from 'vitest'
import {
  hasConfigChanges,
  toConfigChanges,
  toOptionalNumber,
  type ConfigValues,
} from '@/modules/config/domain/entities/ScraperConfig'

const ORIGINAL: ConfigValues = {
  keywords: ['django'],
  limit: 3,
  maxAgeHours: 72,
  proxyUrl: null,
  sites: [{ name: 'upwork', isEnabled: true, limit: 30 }],
}

describe('toConfigChanges', () => {
  it('sends nothing when nothing changed', () => {
    expect(hasConfigChanges(toConfigChanges(ORIGINAL, ORIGINAL, []))).toBe(false)
  })

  it('sends only the changed field', () => {
    const changes = toConfigChanges({ ...ORIGINAL, limit: 9 }, ORIGINAL, [])

    expect(changes).toEqual({ limit: 9 })
  })

  it('sends a cleared proxy', () => {
    const original = { ...ORIGINAL, proxyUrl: 'socks5://localhost:1080' }

    expect(toConfigChanges(ORIGINAL, original, [])).toEqual({ proxyUrl: null })
  })

  it('sends only the changed site field', () => {
    const values = { ...ORIGINAL, sites: [{ name: 'upwork', isEnabled: false, limit: 30 }] }

    expect(toConfigChanges(values, ORIGINAL, [])).toEqual({
      sites: { upwork: { isEnabled: false } },
    })
  })

  it('leaves out locked fields', () => {
    const values = {
      ...ORIGINAL,
      proxyUrl: 'socks5://localhost:9999',
      sites: [{ name: 'upwork', isEnabled: true, limit: 50 }],
    }

    expect(toConfigChanges(values, ORIGINAL, ['proxy', 'sites.upwork.limit'])).toEqual({})
  })

  it('leaves out emptied limits', () => {
    const values = {
      ...ORIGINAL,
      limit: null,
      sites: [{ name: 'upwork', isEnabled: true, limit: null }],
    }

    expect(toConfigChanges(values, ORIGINAL, [])).toEqual({})
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
