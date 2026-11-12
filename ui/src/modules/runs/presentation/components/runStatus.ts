import type { RunRecord, RunStatus } from '@/modules/runs/domain/entities/Run'
import type { BadgeVariants } from '@/shared/components/ui/badge'

interface RunStatusView {
  label: string
  tone: NonNullable<BadgeVariants['tone']>
}

export const RUN_STATUS_VIEWS: Record<RunStatus, RunStatusView> = {
  running: { label: 'Running', tone: 'neutral' },
  succeeded: { label: 'Succeeded', tone: 'accent' },
  partial: { label: 'Partial', tone: 'neutral' },
  failed: { label: 'Failed', tone: 'danger' },
  interrupted: { label: 'Interrupted', tone: 'danger' },
}

export function formatJobCount(count: number): string {
  return count === 1 ? '1 job' : `${count} jobs`
}

export type RunTone = RunStatusView['tone']

export const DISCORD_TONE_CLASSES: Record<RunTone, string> = {
  neutral: 'text-ink-muted',
  accent: 'text-accent',
  danger: 'text-danger',
}

export type DiscordToastKind = 'success' | 'warning' | 'error'

export interface DiscordStatusView {
  label: string
  tone: RunTone
  toastKind: DiscordToastKind
}

export function toDiscordStatusView(record: RunRecord): DiscordStatusView | null {
  switch (record.discordStatus) {
    case 'sending':
      return { label: 'Sending to Discord', tone: 'neutral', toastKind: 'success' }
    case 'sent':
      return {
        label: `Sent ${record.discordSent} to Discord`,
        tone: 'accent',
        toastKind: 'success',
      }
    case 'partial':
      return {
        label: `Sent ${record.discordSent}, failed ${record.discordFailed} on Discord`,
        tone: 'neutral',
        toastKind: 'warning',
      }
    case 'failed':
      return {
        label:
          record.discordError === null
            ? 'Discord failed'
            : `Discord failed: ${record.discordError}`,
        tone: 'danger',
        toastKind: 'error',
      }
    default:
      return null
  }
}
