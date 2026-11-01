import type { ConfigChanges, ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'

export interface ConfigRepository {
  getConfig(): Promise<ConfigSnapshot>
  saveConfig(changes: ConfigChanges): Promise<void>
}
