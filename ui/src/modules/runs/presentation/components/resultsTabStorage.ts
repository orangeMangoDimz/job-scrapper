// The one list of tab ids: the types, the guard and the view all derive from it
export const JSON_TABS = ['raw', 'filtered'] as const
export const RESULTS_TABS = ['cards', ...JSON_TABS] as const

export type JsonTab = (typeof JSON_TABS)[number]
export type ResultsTab = (typeof RESULTS_TABS)[number]

export type ResultsTabStorage = Pick<Storage, 'getItem' | 'setItem'>

export const RESULTS_TAB_STORAGE_KEY = 'scraper-ui:runs:results-tab'
export const DEFAULT_RESULTS_TAB: ResultsTab = 'cards'

export function isResultsTab(value: unknown): value is ResultsTab {
  return RESULTS_TABS.some((tab) => tab === value)
}

function browserStorage(): ResultsTabStorage {
  return window.localStorage
}

export function readResultsTab(getStorage: () => ResultsTabStorage = browserStorage): ResultsTab {
  try {
    const stored = getStorage().getItem(RESULTS_TAB_STORAGE_KEY)
    return isResultsTab(stored) ? stored : DEFAULT_RESULTS_TAB
  } catch {
    return DEFAULT_RESULTS_TAB
  }
}

export function writeResultsTab(
  tab: ResultsTab,
  getStorage: () => ResultsTabStorage = browserStorage,
): void {
  try {
    getStorage().setItem(RESULTS_TAB_STORAGE_KEY, tab)
  } catch {
    // Storage can be blocked, the tab still works for this visit
  }
}
