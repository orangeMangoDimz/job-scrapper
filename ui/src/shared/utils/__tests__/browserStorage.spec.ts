import { describe, expect, it, vi } from 'vitest'
import { createMemoryStorage } from '@/__tests__/memoryStorage'
import {
  readStorageFlag,
  readStorageItem,
  writeStorageFlag,
  writeStorageItem,
  type KeyValueStorage,
} from '@/shared/utils/browserStorage'

const KEY = 'scraper-ui:test'

function memoryStorage(initial: Record<string, string> = {}): KeyValueStorage & {
  values: Record<string, string>
} {
  const values = { ...initial }
  return {
    values,
    getItem: (key) => values[key] ?? null,
    setItem: (key, value) => {
      values[key] = value
    },
  }
}

const throwingStorage: KeyValueStorage = {
  getItem: () => {
    throw new Error('blocked')
  },
  setItem: () => {
    throw new Error('blocked')
  },
}

describe('browserStorage', () => {
  it('reads a stored item', () => {
    expect(readStorageItem(KEY, () => memoryStorage({ [KEY]: 'cards' }))).toBe('cards')
  })

  it('reads null when nothing is stored', () => {
    expect(readStorageItem(KEY, () => memoryStorage())).toBeNull()
  })

  it('reads null when storage throws', () => {
    expect(readStorageItem(KEY, () => throwingStorage)).toBeNull()
  })

  it('reads null when getting the storage throws', () => {
    expect(
      readStorageItem(KEY, () => {
        throw new Error('blocked')
      }),
    ).toBeNull()
  })

  it('writes an item and reports success', () => {
    const storage = memoryStorage()

    expect(writeStorageItem(KEY, 'raw', () => storage)).toBe(true)
    expect(storage.values[KEY]).toBe('raw')
  })

  it('reports a failed write without throwing', () => {
    expect(writeStorageItem(KEY, 'raw', () => throwingStorage)).toBe(false)
  })

  it('reads a flag that was stored on', () => {
    expect(readStorageFlag(KEY, () => memoryStorage({ [KEY]: 'true' }))).toBe(true)
  })

  it('reads a flag that was stored off', () => {
    expect(readStorageFlag(KEY, () => memoryStorage({ [KEY]: 'false' }))).toBe(false)
  })

  it('reads a flag as off when nothing valid is stored', () => {
    expect(readStorageFlag(KEY, () => memoryStorage())).toBe(false)
    expect(readStorageFlag(KEY, () => memoryStorage({ [KEY]: 'yes' }))).toBe(false)
    expect(readStorageFlag(KEY, () => throwingStorage)).toBe(false)
  })

  it('writes a flag as true or false', () => {
    const storage = memoryStorage()

    writeStorageFlag(KEY, true, () => storage)
    expect(storage.values[KEY]).toBe('true')

    writeStorageFlag(KEY, false, () => storage)
    expect(storage.values[KEY]).toBe('false')
  })

  it('reports a failed flag write without throwing', () => {
    expect(writeStorageFlag(KEY, true, () => throwingStorage)).toBe(false)
  })

  it('uses window.localStorage by default', () => {
    vi.stubGlobal('localStorage', createMemoryStorage())

    writeStorageItem(KEY, 'filtered')
    expect(window.localStorage.getItem(KEY)).toBe('filtered')
    expect(readStorageItem(KEY)).toBe('filtered')

    writeStorageFlag(KEY, true)
    expect(readStorageFlag(KEY)).toBe(true)
    vi.unstubAllGlobals()
  })
})
