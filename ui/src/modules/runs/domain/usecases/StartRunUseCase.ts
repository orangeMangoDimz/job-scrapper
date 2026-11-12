import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import type { RunRepository } from '@/modules/runs/domain/repositories/RunRepository'

export class StartRunUseCase {
  private readonly repository: RunRepository

  constructor(repository: RunRepository) {
    this.repository = repository
  }

  execute(keywords: string[], sites: string[], notifyDiscord: boolean): Promise<RunRecord> {
    return this.repository.startRun(keywords, sites, notifyDiscord)
  }
}
