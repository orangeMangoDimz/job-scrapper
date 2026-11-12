import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import { createMemoryStorage } from '@/__tests__/memoryStorage'
import type { RunOptions } from '@/modules/runs/domain/entities/Run'
import type { NotifyDiscordBlock } from '@/modules/runs/presentation/components/notifyDiscordBlock'
import RunForm from '@/modules/runs/presentation/components/RunForm.vue'
import { NOTIFY_DISCORD_STORAGE_KEY } from '@/modules/runs/presentation/components/notifyDiscordStorage'

const OPTIONS: RunOptions = {
  keywords: ['django'],
  sites: [
    { name: 'upwork', isEnabled: true },
    { name: 'indeed', isEnabled: false },
  ],
  isStale: false,
}

type Props = {
  isRunning?: boolean
  discordBlock?: NotifyDiscordBlock | null
  hasUnsavedConfig?: boolean
}

function mountForm(props: Props = {}) {
  return mount(RunForm, {
    props: { options: OPTIONS, isRunning: false, discordBlock: null, ...props },
    global: { stubs: { RouterLink: RouterLinkStub } },
    attachTo: document.body,
  })
}

type Wrapper = ReturnType<typeof mountForm>

function notifyBox(wrapper: Wrapper) {
  return wrapper.get('#run-notify-discord')
}

function runButton(wrapper: Wrapper) {
  return wrapper.get('button[type="submit"]')
}

async function typeKeywords(wrapper: Wrapper) {
  await wrapper.get('#run-keywords').setValue('django, vue')
}

describe('RunForm', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createMemoryStorage())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('has the Send to Discord when done checkbox, off by default', () => {
    const wrapper = mountForm()

    expect(wrapper.text()).toContain('Send to Discord when done')
    expect(notifyBox(wrapper).attributes('data-state')).toBe('unchecked')
    expect(notifyBox(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('emits start with notify false by default', async () => {
    const wrapper = mountForm()
    await typeKeywords(wrapper)

    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('start')).toEqual([[['django', 'vue'], ['upwork'], false]])
  })

  it('emits start with notify true once the box is checked', async () => {
    const wrapper = mountForm()
    await typeKeywords(wrapper)

    await notifyBox(wrapper).trigger('click')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('start')).toEqual([[['django', 'vue'], ['upwork'], true]])
  })

  it('remembers the choice', async () => {
    const wrapper = mountForm()

    await notifyBox(wrapper).trigger('click')

    expect(localStorage.getItem(NOTIFY_DISCORD_STORAGE_KEY)).toBe('true')
    wrapper.unmount()
    expect(notifyBox(mountForm()).attributes('data-state')).toBe('checked')
  })

  describe('when Discord cannot be used', () => {
    it.each<[NotifyDiscordBlock, string]>([
      ['not-configured', 'Save a bot token on the Discord page'],
      ['no-channel', 'Set a default channel on the Discord page'],
    ])('disables the checkbox and says what to do for %s', (discordBlock, hint) => {
      const wrapper = mountForm({ discordBlock })

      expect(notifyBox(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain(hint)
    })

    it.each<NotifyDiscordBlock>(['not-configured', 'no-channel'])(
      'links to the Discord page for %s',
      (discordBlock) => {
        const wrapper = mountForm({ discordBlock })

        expect(wrapper.getComponent(RouterLinkStub).props('to')).toEqual({
          path: '/',
          hash: '#discord',
        })
      },
    )

    it('disables the checkbox but shows no hint while the settings load', () => {
      const wrapper = mountForm({ discordBlock: 'loading' })

      expect(notifyBox(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.find('[data-slot="discord-hint"]').exists()).toBe(false)
      expect(wrapper.findComponent(RouterLinkStub).exists()).toBe(false)
    })

    it('says the settings could not load', () => {
      const wrapper = mountForm({ discordBlock: 'load-failed' })

      expect(notifyBox(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain('Could not load Discord settings')
    })

    it('shows no hint or link when Discord is ready', () => {
      const wrapper = mountForm()

      expect(wrapper.find('[data-slot="discord-hint"]').exists()).toBe(false)
      expect(wrapper.findComponent(RouterLinkStub).exists()).toBe(false)
    })

    it('shows the box unchecked even when it was remembered on', () => {
      localStorage.setItem(NOTIFY_DISCORD_STORAGE_KEY, 'true')

      const wrapper = mountForm({ discordBlock: 'no-channel' })

      expect(notifyBox(wrapper).attributes('data-state')).toBe('unchecked')
    })

    it('emits start with notify false even when it was remembered on', async () => {
      localStorage.setItem(NOTIFY_DISCORD_STORAGE_KEY, 'true')
      const wrapper = mountForm({ discordBlock: 'no-channel' })
      await typeKeywords(wrapper)

      await wrapper.get('form').trigger('submit')

      expect(wrapper.emitted('start')).toEqual([[['django', 'vue'], ['upwork'], false]])
    })
  })

  describe('unsaved config', () => {
    it('lets the run start by default', async () => {
      const wrapper = mountForm()
      await typeKeywords(wrapper)

      expect(runButton(wrapper).attributes('disabled')).toBeUndefined()
      expect(wrapper.text()).not.toContain('Save or discard config changes first')
    })

    it('blocks Run scrape and says why', async () => {
      const wrapper = mountForm({ hasUnsavedConfig: true })
      await typeKeywords(wrapper)

      expect(runButton(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain('Save or discard config changes first')
    })

    it('links to the config card', () => {
      const wrapper = mountForm({ hasUnsavedConfig: true })

      expect(wrapper.getComponent(RouterLinkStub).props('to')).toEqual({
        path: '/',
        hash: '#config',
      })
    })
  })

  it('blocks Run scrape while a run is going', async () => {
    const wrapper = mountForm({ isRunning: true })
    await typeKeywords(wrapper)

    expect(runButton(wrapper).attributes('disabled')).toBeDefined()
    expect(runButton(wrapper).text()).toBe('Scrape running')
  })
})
