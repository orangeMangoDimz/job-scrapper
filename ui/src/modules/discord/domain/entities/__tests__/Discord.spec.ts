import { describe, expect, it } from 'vitest'
import {
  countChars,
  toMentionPrefix,
  toSendSummary,
  toSettingsChanges,
  toSettingsForm,
  type DiscordSettings,
} from '@/modules/discord/domain/entities/Discord'

const SETTINGS: DiscordSettings = {
  isConfigured: true,
  tokenHint: '••••1234',
  defaultChannelId: '12345678901234567',
  mentionUserId: null,
  messageTemplate: '{title} at {company}',
  maxChars: 1900,
  updatedAt: '2026-11-11T01:00:00+00:00',
}

describe('toSettingsForm', () => {
  it('turns every value into text and leaves the token empty', () => {
    expect(toSettingsForm(SETTINGS)).toEqual({
      token: '',
      defaultChannelId: '12345678901234567',
      mentionUserId: '',
      messageTemplate: '{title} at {company}',
      maxChars: '1900',
    })
  })
})

describe('toSettingsChanges', () => {
  it('sends nothing when the form is the same as the saved settings', () => {
    const changes = toSettingsChanges(toSettingsForm(SETTINGS), SETTINGS)

    expect(changes).toEqual({})
  })

  it('leaves the token out when its box is empty', () => {
    const changes = toSettingsChanges(toSettingsForm(SETTINGS), SETTINGS)

    expect(changes).not.toHaveProperty('token')
  })

  it('leaves the token out when its box only has spaces', () => {
    const changes = toSettingsChanges({ ...toSettingsForm(SETTINGS), token: '   ' }, SETTINGS)

    expect(changes).not.toHaveProperty('token')
  })

  it('sends only a typed token without the spaces around it', () => {
    const changes = toSettingsChanges({ ...toSettingsForm(SETTINGS), token: ' abc.def ' }, SETTINGS)

    expect(changes).toEqual({ token: 'abc.def' })
  })

  it('sends null for a cleared channel or user id', () => {
    const settings = { ...SETTINGS, mentionUserId: '76543210987654321' }
    const changes = toSettingsChanges(
      { ...toSettingsForm(settings), defaultChannelId: '  ', mentionUserId: '' },
      settings,
    )

    expect(changes).toEqual({ defaultChannelId: null, mentionUserId: null })
  })

  it('leaves an id out when it was empty and still is', () => {
    const changes = toSettingsChanges(
      { ...toSettingsForm(SETTINGS), mentionUserId: '  ' },
      SETTINGS,
    )

    expect(changes).not.toHaveProperty('mentionUserId')
  })

  it('leaves an id out when only the spaces around it differ', () => {
    const changes = toSettingsChanges(
      { ...toSettingsForm(SETTINGS), defaultChannelId: ' 12345678901234567 ' },
      SETTINGS,
    )

    expect(changes).toEqual({})
  })

  it('sends only the template when only the template changed', () => {
    const changes = toSettingsChanges(
      { ...toSettingsForm(SETTINGS), messageTemplate: '{title}' },
      SETTINGS,
    )

    expect(changes).toEqual({ messageTemplate: '{title}' })
  })

  it('sends only max chars when only max chars changed', () => {
    const changes = toSettingsChanges({ ...toSettingsForm(SETTINGS), maxChars: '1500' }, SETTINGS)

    expect(changes).toEqual({ maxChars: 1500 })
  })

  it('sends every field that changed', () => {
    const changes = toSettingsChanges(
      {
        token: 'abc.def',
        defaultChannelId: '22345678901234567',
        mentionUserId: '76543210987654321',
        messageTemplate: '{title}',
        maxChars: '1500',
      },
      SETTINGS,
    )

    expect(changes).toEqual({
      token: 'abc.def',
      defaultChannelId: '22345678901234567',
      mentionUserId: '76543210987654321',
      messageTemplate: '{title}',
      maxChars: 1500,
    })
  })
})

describe('toMentionPrefix', () => {
  it('is the user tag and a new line when mention is on', () => {
    expect(toMentionPrefix('76543210987654321', true)).toBe('<@76543210987654321>\n')
  })

  it('is empty when mention is off or there is no user id', () => {
    expect(toMentionPrefix('76543210987654321', false)).toBe('')
    expect(toMentionPrefix(null, true)).toBe('')
  })
})

describe('countChars', () => {
  it('counts a character outside the basic plane once', () => {
    expect(countChars('a😀b')).toBe(3)
  })
})

describe('toSendSummary', () => {
  it('names the sent messages when none failed', () => {
    expect(toSendSummary({ sent: 3, failed: 0, results: [] })).toBe('Sent 3 messages')
    expect(toSendSummary({ sent: 1, failed: 0, results: [] })).toBe('Sent 1 message')
  })

  it('names the failed messages too', () => {
    expect(toSendSummary({ sent: 2, failed: 1, results: [] })).toBe('Sent 2, 1 failed')
  })

  it('says nothing was sent when all failed', () => {
    expect(toSendSummary({ sent: 0, failed: 2, results: [] })).toBe('Nothing was sent, 2 failed')
  })
})
