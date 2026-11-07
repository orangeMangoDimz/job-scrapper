import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { navGroups } from '@/router/navigation'
import AppSidebar from '@/shared/components/AppSidebar.vue'
import { SidebarProvider } from '@/shared/components/ui/sidebar'
import { useThemeStore } from '@/shared/stores/useThemeStore'

function stubBrowser(): void {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn<ResizeObserver['observe']>()
      unobserve = vi.fn<ResizeObserver['unobserve']>()
      disconnect = vi.fn<ResizeObserver['disconnect']>()
    },
  )
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn<MediaQueryList['addEventListener']>(),
      removeEventListener: vi.fn<MediaQueryList['removeEventListener']>(),
      addListener: vi.fn<MediaQueryList['addListener']>(),
      removeListener: vi.fn<MediaQueryList['removeListener']>(),
    })),
  )
}

async function mountSidebar(path: string, canSignOut = true) {
  stubBrowser()
  const blank = { render: () => null }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/runs', component: blank },
      { path: '/config', component: blank },
    ],
  })
  router.push(path)
  await router.isReady()

  const Host = defineComponent({
    emits: ['signOut'],
    setup(_, { emit }) {
      return () =>
        h(SidebarProvider, null, () =>
          h(AppSidebar, { groups: navGroups, canSignOut, onSignOut: () => emit('signOut') }),
        )
    },
  })

  const wrapper = mount(Host, {
    global: { plugins: [router, createPinia()] },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

async function openAdminMenu(): Promise<HTMLElement> {
  document.body
    .querySelector('[data-slot="dropdown-menu-trigger"]')!
    .dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  await flushPromises()
  return document.body.querySelector<HTMLElement>('[role="menu"]')!
}

function menuRows(menu: HTMLElement): (string | undefined)[] {
  return [...menu.querySelectorAll('[role="menuitem"], [role="menuitemradio"]')].map((row) =>
    row.textContent?.trim(),
  )
}

describe('AppSidebar', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('shows the NoNo Scraper wordmark', async () => {
    const wrapper = await mountSidebar('/runs')

    expect(wrapper.get('[data-slot="sidebar-header"]').text()).toContain('NoNo Scraper')
  })

  it('links to Runs and Config inside the Main navigation', async () => {
    const wrapper = await mountSidebar('/runs')
    const nav = wrapper.get('nav[aria-label="Main"]')

    expect(nav.findAll('a').map((link) => link.attributes('href'))).toEqual(['/runs', '/config'])
    expect(nav.text()).toContain('Runs')
    expect(nav.text()).toContain('Config')
  })

  it('marks only the link for the current page', async () => {
    const wrapper = await mountSidebar('/config')

    expect(wrapper.get('a[href="/config"]').attributes('aria-current')).toBe('page')
    expect(wrapper.get('a[href="/runs"]').attributes('aria-current')).toBeUndefined()
  })

  it('labels the footer menu Admin', async () => {
    const wrapper = await mountSidebar('/runs')
    const trigger = wrapper.get('[data-slot="dropdown-menu-trigger"]')

    expect(trigger.text()).toContain('Admin')
    expect(trigger.attributes('aria-expanded')).toBe('false')
  })

  it('offers the theme options and Sign out in the Admin menu', async () => {
    await mountSidebar('/runs')
    const menu = await openAdminMenu()

    expect(menuRows(menu)).toEqual(['Light', 'Dark', 'System', 'Sign out'])
  })

  it('leaves Sign out out of the menu when sign-in is turned off', async () => {
    await mountSidebar('/runs', false)
    const menu = await openAdminMenu()

    expect(menuRows(menu)).toEqual(['Light', 'Dark', 'System'])
    expect(menu.querySelectorAll('[data-slot="dropdown-menu-separator"]')).toHaveLength(0)
  })

  it('sets the theme chosen from the Admin menu', async () => {
    await mountSidebar('/runs')
    const menu = await openAdminMenu()
    const dark = [...menu.querySelectorAll<HTMLElement>('[role="menuitemradio"]')].find(
      (option) => option.textContent?.trim() === 'Dark',
    )!

    dark.click()
    await flushPromises()

    expect(useThemeStore().mode).toBe('dark')
  })

  it('asks for confirmation before emitting signOut', async () => {
    const wrapper = await mountSidebar('/runs')
    const menu = await openAdminMenu()
    const signOut = [...menu.querySelectorAll<HTMLElement>('[role="menuitem"]')].find(
      (item) => item.textContent?.trim() === 'Sign out',
    )!

    signOut.click()
    await flushPromises()
    expect(wrapper.emitted('signOut')).toBeUndefined()

    const dialog = document.body.querySelector('[role="dialog"]')!
    const confirm = [...dialog.querySelectorAll<HTMLButtonElement>('button')].find(
      (button) => button.textContent?.trim() === 'Sign out',
    )!
    confirm.click()
    await flushPromises()

    expect(wrapper.emitted('signOut')).toHaveLength(1)
  })
})
