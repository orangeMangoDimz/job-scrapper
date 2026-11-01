import type { Session } from '@/modules/auth/domain/entities/Session'

export interface AuthRepository {
  getSession(): Promise<Session>
  login(password: string): Promise<void>
  logout(): Promise<void>
}
