import { describe, expect, it } from 'vitest'
import {
  toDiscordBot,
  toDiscordChannels,
  toDiscordContentModel,
  toDiscordMessages,
  toDiscordSendResult,
  toDiscordSettings,
  toDiscordSettingsChangesModel,
} from '@/modules/discord/data/models/DiscordModel'

describe('toDiscordSettings', () => {
  it('maps API names', () => {
    expect(
      toDiscordSettings({
        configured: true,
        token_hint: '••••1234',
        default_channel_id: '12345678901234567',
        mention_user_id: null,
        message_template: '{title}',
        max_chars: 1900,
        updated_at: '2026-11-11T01:00:00+00:00',
      }),
    ).toEqual({
      isConfigured: true,
      tokenHint: '••••1234',
      defaultChannelId: '12345678901234567',
      mentionUserId: null,
      messageTemplate: '{title}',
      maxChars: 1900,
      updatedAt: '2026-11-11T01:00:00+00:00',
    })
  })

  it('keeps the empty values empty', () => {
    const settings = toDiscordSettings({
      configured: false,
      token_hint: null,
      default_channel_id: null,
      mention_user_id: null,
      message_template: '{title}',
      max_chars: 1900,
      updated_at: null,
    })

    expect(settings.isConfigured).toBe(false)
    expect(settings.tokenHint).toBeNull()
    expect(settings.updatedAt).toBeNull()
  })
})

describe('toDiscordSettingsChangesModel', () => {
  it('maps changes to API names and keeps null', () => {
    expect(
      toDiscordSettingsChangesModel({
        token: 'abc',
        defaultChannelId: null,
        mentionUserId: '76543210987654321',
        messageTemplate: '{title}',
        maxChars: 1500,
      }),
    ).toEqual({
      token: 'abc',
      default_channel_id: null,
      mention_user_id: '76543210987654321',
      message_template: '{title}',
      max_chars: 1500,
    })
  })

  it('leaves out what was not given', () => {
    expect(toDiscordSettingsChangesModel({ maxChars: 1500 })).toEqual({ max_chars: 1500 })
  })
})

describe('toDiscordBot', () => {
  it('maps API names', () => {
    expect(toDiscordBot({ bot_name: 'Jobs', bot_id: '42' })).toEqual({ name: 'Jobs', id: '42' })
  })
})

describe('toDiscordChannels', () => {
  it('maps API names', () => {
    expect(
      toDiscordChannels({
        channels: [{ id: '1', name: 'jobs', guild_id: '2', guild_name: 'Home' }],
      }),
    ).toEqual([{ id: '1', name: 'jobs', guildId: '2', guildName: 'Home' }])
  })
})

describe('toDiscordContentModel', () => {
  it('sends free text as text', () => {
    expect(toDiscordContentModel({ kind: 'text', text: 'hi' })).toEqual({ text: 'hi' })
  })

  it('sends jobs as a run id and job indexes', () => {
    expect(toDiscordContentModel({ kind: 'jobs', runId: 'r1', jobIndexes: [0, 2] })).toEqual({
      run_id: 'r1',
      job_indexes: [0, 2],
    })
  })
})

describe('toDiscordMessages', () => {
  it('takes the messages list', () => {
    expect(toDiscordMessages({ messages: ['a', 'b'] })).toEqual(['a', 'b'])
  })
})

describe('toDiscordSendResult', () => {
  it('maps every message result', () => {
    expect(
      toDiscordSendResult({
        sent: 1,
        failed: 1,
        results: [
          {
            index: 0,
            kind: 'job',
            title: 'Dev',
            status: 'sent',
            message_id: '9',
            error: null,
          },
          {
            index: 1,
            kind: 'summary',
            title: null,
            status: 'failed',
            message_id: null,
            error: 'Rate limited',
          },
        ],
      }),
    ).toEqual({
      sent: 1,
      failed: 1,
      results: [
        { index: 0, kind: 'job', title: 'Dev', status: 'sent', messageId: '9', error: null },
        {
          index: 1,
          kind: 'summary',
          title: null,
          status: 'failed',
          messageId: null,
          error: 'Rate limited',
        },
      ],
    })
  })
})
