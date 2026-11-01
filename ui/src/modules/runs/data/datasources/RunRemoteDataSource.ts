import type { HttpClient } from '@/core/http/httpClient'
import type {
  RunDetailModel,
  RunOptionsModel,
  RunRecordModel,
} from '@/modules/runs/data/models/RunModel'

const SITES_PATH = '/sites'
const RUNS_PATH = '/runs'

export class RunRemoteDataSource {
  private readonly client: HttpClient

  constructor(client: HttpClient) {
    this.client = client
  }

  getOptions(): Promise<RunOptionsModel> {
    return this.client.get<RunOptionsModel>(SITES_PATH)
  }

  listRuns(): Promise<RunRecordModel[]> {
    return this.client.get<RunRecordModel[]>(RUNS_PATH)
  }

  getRun(id: string): Promise<RunDetailModel> {
    return this.client.get<RunDetailModel>(`${RUNS_PATH}/${encodeURIComponent(id)}`)
  }

  startRun(keywords: string[], sites: string[]): Promise<RunRecordModel> {
    return this.client.post<RunRecordModel>(RUNS_PATH, { keywords, sites })
  }
}
