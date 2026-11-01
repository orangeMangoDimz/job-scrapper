import type { ConfigRemoteDataSource } from '@/modules/config/data/datasources/ConfigRemoteDataSource'
import {
  toConfigChangesModel,
  toConfigSnapshot,
  toConfigVersions,
} from '@/modules/config/data/models/ConfigModel'
import type {
  ConfigChanges,
  ConfigSnapshot,
  ConfigVersion,
} from '@/modules/config/domain/entities/ScraperConfig'
import type { ConfigRepository } from '@/modules/config/domain/repositories/ConfigRepository'

export class ConfigRepositoryImpl implements ConfigRepository {
  private readonly dataSource: ConfigRemoteDataSource

  constructor(dataSource: ConfigRemoteDataSource) {
    this.dataSource = dataSource
  }

  async getConfig(): Promise<ConfigSnapshot> {
    return toConfigSnapshot(await this.dataSource.getConfig())
  }

  saveConfig(changes: ConfigChanges, version: number): Promise<void> {
    return this.dataSource.saveConfig(toConfigChangesModel(changes), version)
  }

  async getConfigHistory(): Promise<ConfigVersion[]> {
    return toConfigVersions(await this.dataSource.getConfigHistory())
  }

  restoreConfig(version: number, expectedVersion: number): Promise<void> {
    return this.dataSource.restoreConfig(version, expectedVersion)
  }
}
