import { describe, expect, it, vi } from 'vitest'
import type { HttpClient } from '@/core/http/httpClient'
import {
  DISCORD_CALL_TIMEOUT_MS,
  DISCORD_SEND_TIMEOUT_MS,
  DiscordRemoteDataSource,
} from '@/modules/discord/data/datasources/DiscordRemoteDataSource'

function makeClient() {
  return {
    get: vi.fn().mockResolvedValue('got'),
    post: vi.fn().mockResolvedValue('posted'),
    put: vi.fn().mockResolvedValue('put'),
  }
}

function makeSource(client: ReturnType<typeof makeClient>): DiscordRemoteDataSource {
  return new DiscordRemoteDataSource(client as unknown as HttpClient)
}

describe('DiscordRemoteDataSource', () => {
  it('gets the settings', async () => {
    const client = makeClient()

    await expect(makeSource(client).getSettings()).resolves.toBe('got')

    expect(client.get).toHaveBeenCalledWith('/discord/settings')
  })

  it('puts the settings changes', async () => {
    const client = makeClient()

    await makeSource(client).saveSettings({ max_chars: 1500 })

    expect(client.put).toHaveBeenCalledWith('/discord/settings', { max_chars: 1500 })
  })

  it('tests the connection with a long wait', async () => {
    const client = makeClient()

    await makeSource(client).testConnection()

    expect(client.post).toHaveBeenCalledWith('/discord/test', undefined, DISCORD_CALL_TIMEOUT_MS)
  })

  it('lists the channels with a long wait', async () => {
    const client = makeClient()

    await makeSource(client).listChannels()

    expect(client.get).toHaveBeenCalledWith('/discord/channels', DISCORD_CALL_TIMEOUT_MS)
  })

  it('previews with the mention flag and the content', async () => {
    const client = makeClient()

    await makeSource(client).previewMessage(true, { text: 'hi' })

    expect(client.post).toHaveBeenCalledWith('/discord/preview', { mention: true, text: 'hi' })
  })

  it('sends with the channel id and a long wait', async () => {
    const client = makeClient()

    await makeSource(client).sendMessage('123', false, { run_id: 'r1', job_indexes: [0, 1] })

    expect(client.post).toHaveBeenCalledWith(
      '/discord/send',
      { channel_id: '123', mention: false, run_id: 'r1', job_indexes: [0, 1] },
      DISCORD_SEND_TIMEOUT_MS,
    )
  })

  it('waits longer for a send than the server does', () => {
    expect(DISCORD_SEND_TIMEOUT_MS).toBeGreaterThan(180_000)
    expect(DISCORD_CALL_TIMEOUT_MS).toBeGreaterThan(20_000)
    expect(DISCORD_CALL_TIMEOUT_MS).toBeGreaterThan(20_000)
  })
})
