import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import AppShell from '@/shared/components/AppShell.vue'

function mountShell() {
  return mount(AppShell, {
    slots: {
      sidebar: '<aside data-test="sidebar-slot">Sidebar content</aside>',
      default: '<h1 data-test="page-slot">Config</h1>',
    },
    attachTo: document.body,
  })
}

describe('AppShell', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('puts the sidebar toggle next to the page title, from md up only', () => {
    const wrapper = mountShell()
    const toggle = wrapper.get('main [data-slot="sidebar-toggle"]')

    expect(toggle.classes()).toEqual(
      expect.arrayContaining(['absolute', '-left-12', 'max-md:hidden']),
    )
    expect(toggle.element.parentElement).toBe(
      wrapper.get('[data-test="page-slot"]').element.parentElement,
    )
  })

  it('collapses and expands the sidebar from the same toggle, keeping focus on it', async () => {
    const wrapper = mountShell()
    const toggle = wrapper.get('[data-slot="sidebar-toggle"]')
    expect(toggle.text()).toBe('Collapse sidebar')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    ;(toggle.element as HTMLElement).focus()

    await toggle.trigger('click')

    expect(toggle.text()).toBe('Expand sidebar')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(toggle.element)

    await toggle.trigger('click')

    expect(toggle.text()).toBe('Collapse sidebar')
    expect(toggle.attributes('aria-expanded')).toBe('true')
  })
})
