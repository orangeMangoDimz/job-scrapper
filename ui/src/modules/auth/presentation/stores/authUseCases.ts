import type { GetSessionUseCase } from '@/modules/auth/domain/usecases/GetSessionUseCase'
import type { LoginUseCase } from '@/modules/auth/domain/usecases/LoginUseCase'
import type { LogoutUseCase } from '@/modules/auth/domain/usecases/LogoutUseCase'

export interface AuthUseCases {
  getSession: Pick<GetSessionUseCase, 'execute'>
  login: Pick<LoginUseCase, 'execute'>
  logout: Pick<LogoutUseCase, 'execute'>
}

let useCases: AuthUseCases | null = null

export function provideAuthUseCases(next: AuthUseCases): void {
  useCases = next
}

export function requireAuthUseCases(): AuthUseCases {
  if (useCases === null) {
    throw new Error('Auth use cases are not provided')
  }
  return useCases
}
