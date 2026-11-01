export type LoadStatus = 'idle' | 'loading' | 'ready' | 'error'

const PENDING_STATUSES: ReadonlySet<string> = new Set(['idle', 'loading'])

export function isPendingStatus(status: string): boolean {
  return PENDING_STATUSES.has(status)
}
