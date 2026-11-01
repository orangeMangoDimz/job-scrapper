import type { ConfigChanges } from '@/modules/config/domain/entities/ScraperConfig'
import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

export class SaveConfigUseCase {
  private readonly repository: ConfigRepository

  constructor(repository: ConfigRepository) {
    this.repository = repository
  }

  execute(changes: ConfigChanges): Promise<void> {
    return this.repository.saveConfig(changes)
  }
}
