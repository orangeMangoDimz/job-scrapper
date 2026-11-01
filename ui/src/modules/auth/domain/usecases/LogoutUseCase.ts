import type { AuthRepository } from '@/modules/auth/domain/repositories/AuthRepository'

export class LogoutUseCase {
  private readonly repository: AuthRepository

  constructor(repository: AuthRepository) {
    this.repository = repository
  }

  execute(): Promise<void> {
    return this.repository.logout()
  }
}
