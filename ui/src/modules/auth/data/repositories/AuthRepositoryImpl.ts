import type { AuthRemoteDataSource } from '@/modules/auth/data/datasources/AuthRemoteDataSource'
import { toSession } from '@/modules/auth/data/models/SessionModel'
import type { Session } from '@/modules/auth/domain/entities/Session'
import type { AuthRepository } from '@/modules/auth/domain/repositories/AuthRepository'

export class AuthRepositoryImpl implements AuthRepository {
  private readonly dataSource: AuthRemoteDataSource

  constructor(dataSource: AuthRemoteDataSource) {
    this.dataSource = dataSource
  }

  async getSession(): Promise<Session> {
    return toSession(await this.dataSource.getSession())
  }

  login(password: string): Promise<void> {
    return this.dataSource.login(password)
  }

  logout(): Promise<void> {
    return this.dataSource.logout()
  }
}
