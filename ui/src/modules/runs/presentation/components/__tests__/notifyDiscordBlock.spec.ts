import { describe, expect, it } from 'vitest'
import type { DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import { toNotifyDiscordBlock } from '@/modules/runs/presentation/components/notifyDiscordBlock'

const SETTINGS: DiscordSettings = {
  isConfigured: true,
  tokenHint: '••••1234',
  defaultChannelId: '12345678901234567',
  mentionUserId: null,
  messageTemplate: '{title}',
  maxChars: 1900,
  updatedAt: null,
}

describe('toNotifyDiscordBlock', () => {
  it('has no block when a bot token and a default channel are set', () => {
    expect(toNotifyDiscordBlock('ready', SETTINGS)).toBeNull()
  })

  it('blocks without a bot token', () => {
    expect(toNotifyDiscordBlock('ready', { ...SETTINGS, isConfigured: false })).toBe(
      'not-configured',
    )
  })

  it('names the missing bot token first when the channel is missing too', () => {
    const settings = { ...SETTINGS, isConfigured: false, defaultChannelId: null }

    expect(toNotifyDiscordBlock('ready', settings)).toBe('not-configured')
  })

  it('blocks without a default channel', () => {
    expect(toNotifyDiscordBlock('ready', { ...SETTINGS, defaultChannelId: null })).toBe(
      'no-channel',
    )
  })

  it.each(['idle', 'loading'] as const)('blocks as loading while the status is %s', (status) => {
    expect(toNotifyDiscordBlock(status, null)).toBe('loading')
  })

  it('blocks as load-failed when the settings could not load', () => {
    expect(toNotifyDiscordBlock('error', null)).toBe('load-failed')
  })

  it('judges loaded settings even while they load again', () => {
    expect(toNotifyDiscordBlock('loading', SETTINGS)).toBeNull()
  })
})
