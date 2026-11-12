export type KeyValueStorage = Pick<Storage, 'getItem' | 'setItem'>

const ON_VALUE = 'true'
const OFF_VALUE = 'false'

export function browserStorage(): KeyValueStorage {
  return window.localStorage
}

export function readStorageItem(
  key: string,
  getStorage: () => KeyValueStorage = browserStorage,
): string | null {
  try {
    return getStorage().getItem(key)
  } catch {
    return null
  }
}

export function writeStorageItem(
  key: string,
  value: string,
  getStorage: () => KeyValueStorage = browserStorage,
): boolean {
  try {
    getStorage().setItem(key, value)
    return true
  } catch {
    return false
  }
}

export function readStorageFlag(
  key: string,
  getStorage: () => KeyValueStorage = browserStorage,
): boolean {
  return readStorageItem(key, getStorage) === ON_VALUE
}

export function writeStorageFlag(
  key: string,
  isOn: boolean,
  getStorage: () => KeyValueStorage = browserStorage,
): boolean {
  return writeStorageItem(key, isOn ? ON_VALUE : OFF_VALUE, getStorage)
}
