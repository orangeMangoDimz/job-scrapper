import type {
  ConfigChanges,
  ConfigSnapshot,
  ConfigVersion,
} from '@/modules/config/domain/entities/ScraperConfig'

export interface ConfigRepository {
  getConfig(): Promise<ConfigSnapshot>
  saveConfig(changes: ConfigChanges, version: number): Promise<void>
  getConfigHistory(): Promise<ConfigVersion[]>
  restoreConfig(version: number, expectedVersion: number): Promise<void>
}
