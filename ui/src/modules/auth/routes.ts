import type { RouteRecordRaw } from 'vue-router'
import { httpClient } from '@/core/http/httpClient'
import { AuthRemoteDataSource } from '@/modules/auth/data/datasources/AuthRemoteDataSource'
import { AuthRepositoryImpl } from '@/modules/auth/data/repositories/AuthRepositoryImpl'
import { GetSessionUseCase } from '@/modules/auth/domain/usecases/GetSessionUseCase'
import { LoginUseCase } from '@/modules/auth/domain/usecases/LoginUseCase'
import { LogoutUseCase } from '@/modules/auth/domain/usecases/LogoutUseCase'
import { provideAuthUseCases } from '@/modules/auth/presentation/stores/authUseCases'

const repository = new AuthRepositoryImpl(new AuthRemoteDataSource(httpClient))

provideAuthUseCases({
  getSession: new GetSessionUseCase(repository),
  login: new LoginUseCase(repository),
  logout: new LogoutUseCase(repository),
})

export const authRoutes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/modules/auth/presentation/pages/LoginPage.vue'),
    meta: { isPublic: true, title: 'Sign in' },
  },
]
