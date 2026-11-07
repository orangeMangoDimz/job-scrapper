import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { provideAuthUseCases } from '@/modules/auth/presentation/stores/authUseCases'
import LoginPage from '@/modules/auth/presentation/pages/LoginPage.vue'

const getSession = { execute: vi.fn() }
const login = { execute: vi.fn() }
const logout = { execute: vi.fn() }

async function mountLogin() {
  const blank = { render: () => null }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', component: LoginPage },
      { path: '/runs', component: blank },
    ],
  })
  router.push('/login')
  await router.isReady()
  const wrapper = mount(LoginPage, {
    global: { plugins: [router, createPinia()] },
    attachTo: document.body,
  })
  return { wrapper, router }
}

function submitButton(wrapper: Awaited<ReturnType<typeof mountLogin>>['wrapper']) {
  return wrapper.get('button[type="submit"]')
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn<MediaQueryList['addEventListener']>(),
        removeEventListener: vi.fn<MediaQueryList['removeEventListener']>(),
      })),
    )
    provideAuthUseCases({ getSession, login, logout })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('names the product in the page heading', async () => {
    const { wrapper } = await mountLogin()

    expect(wrapper.get('h1').text()).toBe('Sign in to NoNo Scraper')
  })

  it('keeps Sign in disabled until a password is typed', async () => {
    const { wrapper } = await mountLogin()

    expect(submitButton(wrapper).attributes('disabled')).toBeDefined()
    await wrapper.get('input').setValue('secret')
    expect(submitButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('shows and hides the password', async () => {
    const { wrapper } = await mountLogin()
    const input = wrapper.get('input')
    const toggle = wrapper.get('button[aria-controls]')

    expect(input.attributes('type')).toBe('password')
    await toggle.trigger('click')
    expect(input.attributes('type')).toBe('text')
    expect(toggle.text()).toContain('Hide')
  })

  it('shows the error under the form after a wrong password', async () => {
    login.execute.mockRejectedValue(new Error('Wrong password.'))
    const { wrapper } = await mountLogin()

    await wrapper.get('input').setValue('nope')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('Wrong password.')
    expect(wrapper.get('input').attributes('aria-invalid')).toBe('true')
  })

  it('goes to Runs after a right password', async () => {
    login.execute.mockResolvedValue(undefined)
    const { wrapper, router } = await mountLogin()

    await wrapper.get('input').setValue('secret')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(login.execute).toHaveBeenCalledWith('secret')
    expect(router.currentRoute.value.path).toBe('/runs')
  })
})
