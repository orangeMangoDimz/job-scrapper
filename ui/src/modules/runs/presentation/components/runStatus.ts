import type { RunStatus } from '@/modules/runs/domain/entities/Run'
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
