import type { RunDetail, RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'

export interface RunRepository {
  getOptions(): Promise<RunOptions>
  listRuns(): Promise<RunRecord[]>
  getRun(id: string): Promise<RunDetail>
  startRun(keywords: string[], sites: string[]): Promise<RunRecord>
}
