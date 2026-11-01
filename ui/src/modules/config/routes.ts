import type { RouteRecordRaw } from 'vue-router'
import { httpClient } from '@/core/http/httpClient'
import { ConfigRemoteDataSource } from '@/modules/config/data/datasources/ConfigRemoteDataSource'
import { ConfigRepositoryImpl } from '@/modules/config/data/repositories/ConfigRepositoryImpl'
import { GetConfigHistoryUseCase } from '@/modules/config/domain/usecases/GetConfigHistoryUseCase'
import { GetConfigUseCase } from '@/modules/config/domain/usecases/GetConfigUseCase'
import { RestoreConfigUseCase } from '@/modules/config/domain/usecases/RestoreConfigUseCase'
import { SaveConfigUseCase } from '@/modules/config/domain/usecases/SaveConfigUseCase'
import { provideConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'

const repository = new ConfigRepositoryImpl(new ConfigRemoteDataSource(httpClient))

provideConfigUseCases({
  getConfig: new GetConfigUseCase(repository),
  saveConfig: new SaveConfigUseCase(repository),
  getConfigHistory: new GetConfigHistoryUseCase(repository),
  restoreConfig: new RestoreConfigUseCase(repository),
})

export const configRoutes: RouteRecordRaw[] = [
  {
    path: '/config',
    name: 'config',
    component: () => import('@/modules/config/presentation/pages/ConfigPage.vue'),
  },
]
