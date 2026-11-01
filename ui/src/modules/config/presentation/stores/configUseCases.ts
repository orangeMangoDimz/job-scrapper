import type { GetConfigHistoryUseCase } from '@/modules/config/domain/usecases/GetConfigHistoryUseCase'
import type { GetConfigUseCase } from '@/modules/config/domain/usecases/GetConfigUseCase'
import type { RestoreConfigUseCase } from '@/modules/config/domain/usecases/RestoreConfigUseCase'
import type { SaveConfigUseCase } from '@/modules/config/domain/usecases/SaveConfigUseCase'

export interface ConfigUseCases {
  getConfig: Pick<GetConfigUseCase, 'execute'>
  saveConfig: Pick<SaveConfigUseCase, 'execute'>
  getConfigHistory: Pick<GetConfigHistoryUseCase, 'execute'>
  restoreConfig: Pick<RestoreConfigUseCase, 'execute'>
}

let useCases: ConfigUseCases | null = null

export function provideConfigUseCases(next: ConfigUseCases): void {
  useCases = next
}

export function requireConfigUseCases(): ConfigUseCases {
  if (useCases === null) {
    throw new Error('Config use cases are not provided')
  }
  return useCases
}
