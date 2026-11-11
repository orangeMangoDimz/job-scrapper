import { createRouter, createWebHistory } from 'vue-router'
import { authRoutes } from '@/modules/auth/routes'
import { configRoutes } from '@/modules/config/routes'
import { discordRoutes } from '@/modules/discord/routes'
import { runRoutes } from '@/modules/runs/routes'
import { createAuthGuard } from '@/router/authGuard'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/runs' },
    ...authRoutes,
    ...runRoutes,
    ...configRoutes,
    ...discordRoutes,
  ],
})

router.beforeEach(createAuthGuard())

export default router
