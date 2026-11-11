import type {
  DiscordSettings,
  DiscordSettingsChanges,
} from '@/modules/discord/domain/entities/Discord'
import type { DiscordRepository } from '@/modules/discord/domain/repositories/DiscordRepository'

export class SaveDiscordSettingsUseCase {
  private readonly repository: DiscordRepository

  constructor(repository: DiscordRepository) {
    this.repository = repository
  }

  execute(changes: DiscordSettingsChanges): Promise<DiscordSettings> {
    return this.repository.saveSettings(changes)
  }
}
