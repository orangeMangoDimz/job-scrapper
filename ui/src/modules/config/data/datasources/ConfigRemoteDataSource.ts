import type { HttpClient } from '@/core/http/httpClient'
import type {
  ConfigChangesModel,
  ConfigHistoryModel,
  ConfigModel,
} from '@/modules/config/data/models/ConfigModel'

const CONFIG_PATH = '/config'
const HISTORY_PATH = '/config/history'
const RESTORE_PATH = '/config/restore'

export class ConfigRemoteDataSource {
  private readonly client: HttpClient

  constructor(client: HttpClient) {
    this.client = client
  }

  getConfig(): Promise<ConfigModel> {
    return this.client.get<ConfigModel>(CONFIG_PATH)
  }

  saveConfig(changes: ConfigChangesModel, version: number): Promise<void> {
    return this.client.put<void>(CONFIG_PATH, { ...changes, version })
  }

  getConfigHistory(): Promise<ConfigHistoryModel> {
    return this.client.get<ConfigHistoryModel>(HISTORY_PATH)
  }

  restoreConfig(version: number, expectedVersion: number): Promise<void> {
    return this.client.post<void>(RESTORE_PATH, { version, expected_version: expectedVersion })
  }
}
