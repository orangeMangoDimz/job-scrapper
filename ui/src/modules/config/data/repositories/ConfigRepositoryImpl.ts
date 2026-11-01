import type { ConfigRemoteDataSource } from '@/modules/config/data/datasources/ConfigRemoteDataSource'
import { toConfigChangesModel, toConfigSnapshot } from '@/modules/config/data/models/ConfigModel'
import type { ConfigChanges, ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

export class ConfigRepositoryImpl implements ConfigRepository {
  private readonly dataSource: ConfigRemoteDataSource

  constructor(dataSource: ConfigRemoteDataSource) {
    this.dataSource = dataSource
  }

  async getConfig(): Promise<ConfigSnapshot> {
    return toConfigSnapshot(await this.dataSource.getConfig())
  }

  saveConfig(changes: ConfigChanges): Promise<void> {
    return this.dataSource.saveConfig(toConfigChangesModel(changes))
  }
}
