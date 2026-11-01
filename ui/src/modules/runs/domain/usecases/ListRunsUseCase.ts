import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import type { RunRepository } from '@/modules/runs/domain/repositories/RunRepository'

export class ListRunsUseCase {
  private readonly repository: RunRepository

  constructor(repository: RunRepository) {
    this.repository = repository
  }

  execute(): Promise<RunRecord[]> {
    return this.repository.listRuns()
  }
}
