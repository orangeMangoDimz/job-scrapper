import type { Session } from '@/modules/auth/domain/entities/Session'
import type { AuthRepository } from '@/modules/auth/domain/repositories/AuthRepository'

export class GetSessionUseCase {
  private readonly repository: AuthRepository

  constructor(repository: AuthRepository) {
    this.repository = repository
  }

  execute(): Promise<Session> {
    return this.repository.getSession()
  }
}
