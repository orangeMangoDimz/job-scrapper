import type { DiscordBot } from '@/modules/discord/domain/entities/Discord'
import type { DiscordRepository } from '@/modules/discord/domain/repositories/DiscordRepository'

export class TestDiscordConnectionUseCase {
  private readonly repository: DiscordRepository

  constructor(repository: DiscordRepository) {
    this.repository = repository
  }

  execute(): Promise<DiscordBot> {
    return this.repository.testConnection()
  }
}
