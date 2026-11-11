import type { DiscordContent } from '@/modules/discord/domain/entities/Discord'
import type { DiscordRepository } from '@/modules/discord/domain/repositories/DiscordRepository'

export class PreviewDiscordMessageUseCase {
  private readonly repository: DiscordRepository

  constructor(repository: DiscordRepository) {
    this.repository = repository
  }

  execute(mention: boolean, content: DiscordContent): Promise<string[]> {
    return this.repository.previewMessage(mention, content)
  }
}
