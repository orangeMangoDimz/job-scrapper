import type { HttpClient } from '@/core/http/httpClient'
import type { ConfigChangesModel, ConfigModel } from '@/modules/config/data/models/ConfigModel'

const CONFIG_PATH = '/config'

export class ConfigRemoteDataSource {
  private readonly client: HttpClient

  constructor(client: HttpClient) {
    this.client = client
  }

  getConfig(): Promise<ConfigModel> {
    return this.client.get<ConfigModel>(CONFIG_PATH)
  }

  saveConfig(changes: ConfigChangesModel): Promise<void> {
    return this.client.put<void>(CONFIG_PATH, changes)
  }
}
