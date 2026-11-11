import type { DiscordChannel } from '@/modules/discord/domain/entities/Discord'
import type { DiscordRepository } from '@/modules/discord/domain/repositories/DiscordRepository'

export class ListDiscordChannelsUseCase {
  private readonly repository: DiscordRepository

  constructor(repository: DiscordRepository) {
    this.repository = repository
  }

  execute(): Promise<DiscordChannel[]> {
    return this.repository.listChannels()
  }
}
