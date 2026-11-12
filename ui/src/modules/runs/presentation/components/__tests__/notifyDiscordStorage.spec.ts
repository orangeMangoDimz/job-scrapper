import { describe, expect, it } from 'vitest'
import {
  NOTIFY_DISCORD_STORAGE_KEY,
  readNotifyDiscord,
  writeNotifyDiscord,
  type NotifyDiscordStorage,
} from '@/modules/runs/presentation/components/notifyDiscordStorage'

function memoryStorage(initial: Record<string, string> = {}) {
  const values = { ...initial }
  const storage: NotifyDiscordStorage = {
    getItem: (key) => values[key] ?? null,
    setItem: (key, value) => {
      values[key] = value
    },
  }
  return { values, storage }
}

const throwingStorage: NotifyDiscordStorage = {
  getItem: () => {
    throw new Error('blocked')
  },
  setItem: () => {
    throw new Error('blocked')
  },
}

describe('notify discord storage', () => {
  it('is off when nothing is stored', () => {
    expect(readNotifyDiscord(() => memoryStorage().storage)).toBe(false)
  })

  it('reads back on', () => {
    const { storage } = memoryStorage({ [NOTIFY_DISCORD_STORAGE_KEY]: 'true' })

    expect(readNotifyDiscord(() => storage)).toBe(true)
  })

  it('reads back off', () => {
    const { storage } = memoryStorage({ [NOTIFY_DISCORD_STORAGE_KEY]: 'false' })

    expect(readNotifyDiscord(() => storage)).toBe(false)
  })

  it('is off for an unknown stored value', () => {
    const { storage } = memoryStorage({ [NOTIFY_DISCORD_STORAGE_KEY]: 'yes' })

    expect(readNotifyDiscord(() => storage)).toBe(false)
  })

  it('is off when reading throws', () => {
    expect(readNotifyDiscord(() => throwingStorage)).toBe(false)
  })

  it('is off when the storage itself cannot be reached', () => {
    expect(
      readNotifyDiscord(() => {
        throw new Error('no storage')
      }),
    ).toBe(false)
  })

  it('writes the choice', () => {
    const { values, storage } = memoryStorage()

    writeNotifyDiscord(true, () => storage)

    expect(values[NOTIFY_DISCORD_STORAGE_KEY]).toBe('true')
  })

  it('does not throw when writing is blocked', () => {
    expect(() => writeNotifyDiscord(true, () => throwingStorage)).not.toThrow()
  })

  it('does not throw when the storage itself cannot be reached', () => {
    expect(() =>
      writeNotifyDiscord(true, () => {
        throw new Error('no storage')
      }),
    ).not.toThrow()
  })
})
