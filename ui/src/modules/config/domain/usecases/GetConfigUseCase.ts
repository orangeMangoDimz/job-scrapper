import type { ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

export class GetConfigUseCase {
  private readonly repository: ConfigRepository

  constructor(repository: ConfigRepository) {
    this.repository = repository
  }

  execute(): Promise<ConfigSnapshot> {
    return this.repository.getConfig()
  }
}
