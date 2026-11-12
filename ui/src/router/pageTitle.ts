import type { Router } from 'vue-router'

export function installPageTitle(router: Router): void {
  router.afterEach((to, from) => {
    const isHashOnly = from.matched.length > 0 && to.path === from.path
    if (!isHashOnly && typeof to.meta.title === 'string') {
      document.title = to.meta.title
    }
  })
}
