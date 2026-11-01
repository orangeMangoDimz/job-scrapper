import type { RunOptions } from '@/modules/runs/domain/entities/Run'
import type { RunRepository } from '@/modules/runs/domain/repositories/RunRepository'

export class GetRunOptionsUseCase {
  private readonly repository: RunRepository

  constructor(repository: RunRepository) {
    this.repository = repository
  }

  execute(): Promise<RunOptions> {
    return this.repository.getOptions()
  }
}
