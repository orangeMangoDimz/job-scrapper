import type { DiscordContent, DiscordSendResult } from '@/modules/discord/domain/entities/Discord'
import type { DiscordRepository } from '@/modules/discord/domain/repositories/DiscordRepository'

export class SendDiscordMessageUseCase {
  private readonly repository: DiscordRepository

  constructor(repository: DiscordRepository) {
    this.repository = repository
  }

  execute(
    channelId: string,
    mention: boolean,
    content: DiscordContent,
  ): Promise<DiscordSendResult> {
    return this.repository.sendMessage(channelId, mention, content)
  }
}
