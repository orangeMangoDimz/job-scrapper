import { ref } from 'vue'
import { defineStore } from 'pinia'
import { requireAuthUseCases } from '@/modules/auth/presentation/stores/authUseCases'
import { toErrorMessage } from '@/shared/utils/errorMessage'

const FALLBACK_ERROR_MESSAGE = 'Could not sign in. Try again.'

export const useAuthStore = defineStore('auth', () => {
  const isAuthRequired = ref(false)
  const isSignedIn = ref(false)
  const isSessionKnown = ref(false)
  const errorMessage = ref<string | null>(null)

  async function ensureSession(): Promise<void> {
    if (isSessionKnown.value) {
      return
    }
    const session = await requireAuthUseCases().getSession.execute()
    isAuthRequired.value = session.isAuthRequired
    isSignedIn.value = session.isSignedIn
    isSessionKnown.value = true
  }

  async function login(password: string): Promise<boolean> {
    errorMessage.value = null
    try {
      await requireAuthUseCases().login.execute(password)
      isSignedIn.value = true
      return true
    } catch (error) {
      errorMessage.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      return false
    }
  }

  async function logout(): Promise<void> {
    await requireAuthUseCases().logout.execute()
    isSignedIn.value = false
  }

  return { isAuthRequired, isSignedIn, errorMessage, ensureSession, login, logout }
})
