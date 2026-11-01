import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

export class RestoreConfigUseCase {
  private readonly repository: ConfigRepository

  constructor(repository: ConfigRepository) {
    this.repository = repository
  }

  execute(version: number, expectedVersion: number): Promise<void> {
    return this.repository.restoreConfig(version, expectedVersion)
  }
}
