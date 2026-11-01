import type { GetRunOptionsUseCase } from '@/modules/runs/domain/usecases/GetRunOptionsUseCase'
import type { GetRunUseCase } from '@/modules/runs/domain/usecases/GetRunUseCase'
import type { ListRunsUseCase } from '@/modules/runs/domain/usecases/ListRunsUseCase'
import type { StartRunUseCase } from '@/modules/runs/domain/usecases/StartRunUseCase'

export interface RunUseCases {
  getOptions: Pick<GetRunOptionsUseCase, 'execute'>
  getRun: Pick<GetRunUseCase, 'execute'>
  listRuns: Pick<ListRunsUseCase, 'execute'>
  startRun: Pick<StartRunUseCase, 'execute'>
}

let useCases: RunUseCases | null = null

export function provideRunUseCases(next: RunUseCases): void {
  useCases = next
}

export function requireRunUseCases(): RunUseCases {
  if (useCases === null) {
    throw new Error('Run use cases are not provided')
  }
  return useCases
}
