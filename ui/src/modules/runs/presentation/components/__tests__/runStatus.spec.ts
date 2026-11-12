import { describe, expect, it } from 'vitest'
import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import { toDiscordStatusView } from '@/modules/runs/presentation/components/runStatus'

function makeRecord(overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    id: 'run-1',
    status: 'succeeded',
    keywords: ['django'],
    sites: ['upwork'],
    startedAt: '2026-11-01T10:00:00+00:00',
    finishedAt: null,
    jobCount: 0,
    errorCount: 0,
    error: null,
    discordStatus: null,
    discordSent: 0,
    discordFailed: 0,
    discordError: null,
    ...overrides,
  }
}

describe('toDiscordStatusView', () => {
  it('shows nothing when there was no send', () => {
    expect(toDiscordStatusView(makeRecord())).toBeNull()
  })

  it('says sending', () => {
    expect(toDiscordStatusView(makeRecord({ discordStatus: 'sending' }))).toEqual({
      label: 'Sending to Discord',
      tone: 'neutral',
      toastKind: 'success',
    })
  })

  it('says how many were sent', () => {
    expect(toDiscordStatusView(makeRecord({ discordStatus: 'sent', discordSent: 5 }))).toEqual({
      label: 'Sent 5 to Discord',
      tone: 'accent',
      toastKind: 'success',
    })
  })

  it('says how many were sent and failed', () => {
    const view = toDiscordStatusView(
      makeRecord({ discordStatus: 'partial', discordSent: 4, discordFailed: 2 }),
    )

    expect(view).toEqual({
      label: 'Sent 4, failed 2 on Discord',
      tone: 'neutral',
      toastKind: 'warning',
    })
  })

  it('says why Discord failed', () => {
    const view = toDiscordStatusView(
      makeRecord({ discordStatus: 'failed', discordError: 'Missing access' }),
    )

    expect(view).toEqual({
      label: 'Discord failed: Missing access',
      tone: 'danger',
      toastKind: 'error',
    })
  })

  it('says Discord failed when there is no reason', () => {
    expect(toDiscordStatusView(makeRecord({ discordStatus: 'failed' }))).toEqual({
      label: 'Discord failed',
      tone: 'danger',
      toastKind: 'error',
    })
  })
})
