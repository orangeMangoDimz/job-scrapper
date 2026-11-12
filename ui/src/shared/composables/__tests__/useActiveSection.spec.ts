import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'

import { useActiveSection } from '@/shared/composables/useActiveSection'

const VIEWPORT_HEIGHT = 1000
const PAGE_HEIGHT = 3000
const IDS = ['runs', 'config', 'discord']

function placeSections(tops: Record<string, number>): void {
  Object.entries(tops).forEach(([id, top]) => {
    const element =
      document.getElementById(id) ?? document.body.appendChild(document.createElement('section'))
    element.id = id
    element.getBoundingClientRect = () => ({ top }) as DOMRect
  })
}

async function scrollWindow(): Promise<void> {
  window.dispatchEvent(new Event('scroll'))
  await nextTick()
}

function mountSpy() {
  let activeId: ReturnType<typeof useActiveSection> | undefined
  const Host = defineComponent({
    setup() {
      activeId = useActiveSection(IDS)
      return () => null
    },
  })
  const wrapper = mount(Host)
  return { wrapper, activeId: () => activeId!.value }
}

describe('useActiveSection', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'innerHeight', { value: VIEWPORT_HEIGHT, configurable: true })
    Object.defineProperty(window, 'scrollY', { value: 0, configurable: true })
    Object.defineProperty(document.documentElement, 'scrollHeight', {
      value: PAGE_HEIGHT,
      configurable: true,
    })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('defaults to the first id when no section has reached the reading line', async () => {
    placeSections({ runs: 300, config: 1400, discord: 2000 })
    const { activeId } = mountSpy()

    await scrollWindow()

    expect(activeId()).toBe('runs')
  })

  it('picks the last section whose top has passed the reading line', async () => {
    placeSections({ runs: -900, config: 120, discord: 900 })
    const { activeId } = mountSpy()

    await scrollWindow()

    expect(activeId()).toBe('config')
  })

  it('moves to the next section as the user scrolls on', async () => {
    placeSections({ runs: -400, config: 120, discord: 1200 })
    const { activeId } = mountSpy()
    await scrollWindow()
    expect(activeId()).toBe('config')

    placeSections({ runs: -900, config: -300, discord: 96 })
    await scrollWindow()

    expect(activeId()).toBe('discord')
  })

  it('picks the last id at the bottom of the page even if its top never reaches the reading line', async () => {
    placeSections({ runs: -2000, config: -800, discord: 600 })
    Object.defineProperty(window, 'scrollY', {
      value: PAGE_HEIGHT - VIEWPORT_HEIGHT,
      configurable: true,
    })
    const { activeId } = mountSpy()

    await scrollWindow()

    expect(activeId()).toBe('discord')
  })

  it('stays on the first id on a short page that cannot scroll', async () => {
    placeSections({ runs: 0, config: 300, discord: 600 })
    Object.defineProperty(document.documentElement, 'scrollHeight', {
      value: VIEWPORT_HEIGHT,
      configurable: true,
    })
    const { activeId } = mountSpy()

    await scrollWindow()

    expect(activeId()).toBe('runs')
  })

  it('does not treat a clicked section as passed when the next one is only just below it', async () => {
    placeSections({ runs: 0, config: 248, discord: 952 })
    const { activeId } = mountSpy()

    await scrollWindow()

    expect(activeId()).toBe('runs')
  })

  it('stops listening once the component unmounts', async () => {
    placeSections({ runs: -400, config: 120, discord: 1200 })
    const { wrapper, activeId } = mountSpy()
    await scrollWindow()
    wrapper.unmount()

    placeSections({ runs: -900, config: -300, discord: 96 })
    await scrollWindow()

    expect(activeId()).toBe('config')
  })
})
