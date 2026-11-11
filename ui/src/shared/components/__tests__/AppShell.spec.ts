import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import AppShell from '@/shared/components/AppShell.vue'

describe('AppShell', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('puts the header above main and the page inside main, with no sidebar', () => {
    const wrapper = mount(AppShell, {
      slots: {
        header: '<header data-test="header-slot">Header</header>',
        default: '<h2 data-test="page-slot">Runs</h2>',
      },
    })

    expect(wrapper.find('main [data-test="header-slot"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="header-slot"]').exists()).toBe(true)
    expect(wrapper.find('main [data-test="page-slot"]').exists()).toBe(true)
    expect(wrapper.find('[data-slot="sidebar"]').exists()).toBe(false)
  })
})
