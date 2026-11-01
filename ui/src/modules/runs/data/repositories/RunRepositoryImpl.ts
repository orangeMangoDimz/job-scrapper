import type { RunRemoteDataSource } from '@/modules/runs/data/datasources/RunRemoteDataSource'
import { toRunDetail, toRunOptions, toRunRecord } from '@/modules/runs/data/models/RunModel'
import type { RunDetail, RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'
import type { RunRepository } from '@/modules/runs/domain/repositories/RunRepository'

export class RunRepositoryImpl implements RunRepository {
  private readonly dataSource: RunRemoteDataSource

  constructor(dataSource: RunRemoteDataSource) {
    this.dataSource = dataSource
  }

  async getOptions(): Promise<RunOptions> {
    return toRunOptions(await this.dataSource.getOptions())
  }

  async listRuns(): Promise<RunRecord[]> {
    const models = await this.dataSource.listRuns()
    return models.map(toRunRecord)
  }

  async getRun(id: string): Promise<RunDetail> {
    return toRunDetail(await this.dataSource.getRun(id))
  }

  async startRun(keywords: string[], sites: string[]): Promise<RunRecord> {
    return toRunRecord(await this.dataSource.startRun(keywords, sites))
  }
}
