import type { DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import type { DiscordRepository } from '@/modules/discord/domain/repositories/DiscordRepository'

export class GetDiscordSettingsUseCase {
  private readonly repository: DiscordRepository

  constructor(repository: DiscordRepository) {
    this.repository = repository
  }

  execute(): Promise<DiscordSettings> {
    return this.repository.getSettings()
  }
}
