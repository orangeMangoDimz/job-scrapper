import type { NavigationGuard } from 'vue-router'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'

export function createAuthGuard(): NavigationGuard {
  return async (to) => {
    const auth = useAuthStore()
    await auth.ensureSession().catch(() => undefined)
    if (to.meta.isPublic === true || auth.isSignedIn) {
      return true
    }
    return { name: 'login' }
  }
}
