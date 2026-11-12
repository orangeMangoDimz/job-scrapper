import type { RouteRecordRaw } from 'vue-router'

export const homeRoutes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    meta: { title: 'Runs' },
    component: () => import('@/modules/home/presentation/pages/HomePage.vue'),
  },
]
