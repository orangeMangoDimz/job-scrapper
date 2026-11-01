import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { provideAuthUseCases } from '@/modules/auth/presentation/stores/authUseCases'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'

const getSession = { execute: vi.fn() }
const login = { execute: vi.fn() }
const logout = { execute: vi.fn() }

describe('useAuthStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    provideAuthUseCases({ getSession, login, logout })
  })

  it('reads the session once', async () => {
    getSession.execute.mockResolvedValue({ isAuthRequired: false, isSignedIn: true })
    const store = useAuthStore()

    await store.ensureSession()
    await store.ensureSession()

    expect(store.isSignedIn).toBe(true)
    expect(getSession.execute).toHaveBeenCalledTimes(1)
  })

  it('signs in after a right password', async () => {
    login.execute.mockResolvedValue(undefined)
    const store = useAuthStore()

    await expect(store.login('secret')).resolves.toBe(true)

    expect(store.isSignedIn).toBe(true)
  })

  it('keeps the error after a wrong password', async () => {
    login.execute.mockRejectedValue(new Error('Wrong password.'))
    const store = useAuthStore()

    await expect(store.login('wrong')).resolves.toBe(false)

    expect(store.errorMessage).toBe('Wrong password.')
    expect(store.isSignedIn).toBe(false)
  })

  it('signs out', async () => {
    login.execute.mockResolvedValue(undefined)
    logout.execute.mockResolvedValue(undefined)
    const store = useAuthStore()
    await store.login('secret')

    await store.logout()

    expect(store.isSignedIn).toBe(false)
  })
})
