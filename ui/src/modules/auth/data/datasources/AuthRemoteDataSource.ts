import type { HttpClient } from '@/core/http/httpClient'
import type { SessionModel } from '@/modules/auth/data/models/SessionModel'

const SESSION_PATH = '/auth/session'
const LOGIN_PATH = '/auth/login'
const LOGOUT_PATH = '/auth/logout'

export class AuthRemoteDataSource {
  private readonly client: HttpClient

  constructor(client: HttpClient) {
    this.client = client
  }

  getSession(): Promise<SessionModel> {
    return this.client.get<SessionModel>(SESSION_PATH)
  }

  login(password: string): Promise<void> {
    return this.client.post<void>(LOGIN_PATH, { password })
  }

  logout(): Promise<void> {
    return this.client.post<void>(LOGOUT_PATH)
  }
}
