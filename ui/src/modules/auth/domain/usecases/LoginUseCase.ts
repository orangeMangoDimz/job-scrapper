import type { AuthRepository } from '@/modules/auth/domain/repositories/AuthRepository'

export class LoginUseCase {
  private readonly repository: AuthRepository

  constructor(repository: AuthRepository) {
    this.repository = repository
  }

  execute(password: string): Promise<void> {
    return this.repository.login(password)
  }
}
