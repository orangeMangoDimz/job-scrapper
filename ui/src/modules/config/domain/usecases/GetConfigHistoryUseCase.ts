import type { ConfigVersion } from '@/modules/config/domain/entities/ScraperConfig'
import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

export class GetConfigHistoryUseCase {
  private readonly repository: ConfigRepository

  constructor(repository: ConfigRepository) {
    this.repository = repository
  }

  execute(): Promise<ConfigVersion[]> {
    return this.repository.getConfigHistory()
  }
}
