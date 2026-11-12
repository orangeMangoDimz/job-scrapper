import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import { configRoutes } from '@/modules/config/routes'
import { useDiscordSettingsStore } from '@/modules/discord/presentation/stores/useDiscordSettingsStore'
import { discordRoutes } from '@/modules/discord/routes'
import HomePage from '@/modules/home/presentation/pages/HomePage.vue'
import { useRunStore } from '@/modules/runs/presentation/stores/useRunStore'
import { runRoutes } from '@/modules/runs/routes'

const PAGE_STUBS = {
  RunsPage: { template: '<h2 id="runs-heading">Runs</h2>' },
  DiscordPage: { template: '<h2 id="discord-heading">Discord</h2>' },
}

async function mountHome(path: string) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: HomePage }],
  })
  router.push(path)
  await router.isReady()
  const wrapper = mount(HomePage, {
    global: { plugins: [router, pinia], stubs: PAGE_STUBS },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

function settleLoads(): void {
  useRunStore().status = 'ready'
  useConfigStore().status = 'ready'
  useDiscordSettingsStore().status = 'error'
}

describe('HomePage', () => {
  const scrollIntoView = vi.fn<Element['scrollIntoView']>()

  beforeEach(() => {
    scrollIntoView.mockReset()
    Element.prototype.scrollIntoView = scrollIntoView
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('stacks Runs and Discord as named sections, with config living inside Runs', async () => {
    const wrapper = await mountHome('/')

    const sections = wrapper.findAll('[data-slot="home-section"]')
    expect(sections.map((section) => section.attributes('id'))).toEqual(['runs', 'discord'])
    expect(sections.map((section) => section.attributes('aria-labelledby'))).toEqual([
      'runs-heading',
      'discord-heading',
    ])
  })

  it('scrolls to the linked section once the first loads settle', async () => {
    await mountHome('/#discord')
    expect(scrollIntoView).not.toHaveBeenCalled()

    settleLoads()
    await flushPromises()

    expect(scrollIntoView).toHaveBeenCalledTimes(1)
    expect(scrollIntoView.mock.contexts[0]).toBe(document.getElementById('discord'))
  })

  it('does not scroll when there is no hash', async () => {
    await mountHome('/')

    settleLoads()
    await flushPromises()

    expect(scrollIntoView).not.toHaveBeenCalled()
  })
})

describe('old page routes', () => {
  it('send /runs, /config and /discord to their section on the single page', () => {
    expect([...runRoutes, ...configRoutes, ...discordRoutes]).toEqual([
      expect.objectContaining({ path: '/runs', redirect: { path: '/', hash: '#runs' } }),
      expect.objectContaining({ path: '/config', redirect: { path: '/', hash: '#config' } }),
      expect.objectContaining({ path: '/discord', redirect: { path: '/', hash: '#discord' } }),
    ])
  })
})

describe('HomePage tab title', () => {
  beforeEach(() => {
    document.title = 'Loading'
    Element.prototype.scrollIntoView = vi.fn()
    Object.defineProperty(document.documentElement, 'scrollHeight', {
      value: 5000,
      configurable: true,
    })
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({ top: 2000 } as DOMRect)
  })

  afterEach(() => {
    document.body.innerHTML = ''
    vi.restoreAllMocks()
  })

  function placeSections(tops: Record<string, number>): void {
    Object.entries(tops).forEach(([id, top]) => {
      const element =
        document.getElementById(id) ?? document.body.appendChild(document.createElement('section'))
      element.id = id
      element.getBoundingClientRect = () => ({ top }) as DOMRect
    })
  }

  it('shows the first section label before anything is scrolled', async () => {
    await mountHome('/')

    expect(document.title).toBe('Runs')
  })

  it('follows a nav link even when the page cannot scroll', async () => {
    const wrapper = await mountHome('/')

    await wrapper.vm.$router.push('/#discord')
    await flushPromises()

    expect(document.title).toBe('Discord')
  })

  it('follows the section the user scrolls to using the nav labels', async () => {
    await mountHome('/')
    placeSections({ config: 120, discord: 900 })
    window.dispatchEvent(new Event('scroll'))
    await flushPromises()
    expect(document.title).toBe('Config')

    placeSections({ config: -300, discord: 96 })
    window.dispatchEvent(new Event('scroll'))
    await flushPromises()

    expect(document.title).toBe('Discord')
  })
})
