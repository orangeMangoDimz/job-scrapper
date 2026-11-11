import { createRouter, createWebHistory } from 'vue-router'
import { authRoutes } from '@/modules/auth/routes'
import { configRoutes } from '@/modules/config/routes'
import { discordRoutes } from '@/modules/discord/routes'
import { homeRoutes } from '@/modules/home/routes'
import { runRoutes } from '@/modules/runs/routes'
import { createAuthGuard } from '@/router/authGuard'

function scrollMotion(): ScrollBehavior {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
}

const router = createRouter({
  history: createWebHistory(),
  routes: [...homeRoutes, ...authRoutes, ...runRoutes, ...configRoutes, ...discordRoutes],
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    }
    if (to.hash) {
      return { el: to.hash, behavior: scrollMotion() }
    }
    return { top: 0 }
  },
})

router.beforeEach(createAuthGuard())

export default router
