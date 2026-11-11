import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import type { DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import DiscordSettingsSection from '@/modules/discord/presentation/components/DiscordSettingsSection.vue'
import { provideDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'

const toastSuccess = vi.hoisted(() => vi.fn())

vi.mock('vue-sonner', () => ({ toast: { success: toastSuccess } }))

const getSettings = { execute: vi.fn() }
const saveSettings = { execute: vi.fn() }
const testConnection = { execute: vi.fn() }
const listChannels = { execute: vi.fn() }
const previewMessage = { execute: vi.fn() }
const sendMessage = { execute: vi.fn() }

const SETTINGS: DiscordSettings = {
  isConfigured: true,
  tokenHint: '••••1234',
  defaultChannelId: '12345678901234567',
  mentionUserId: '76543210987654321',
  messageTemplate: '{title} at {company}',
  maxChars: 1900,
  updatedAt: null,
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function mountSection() {
  return mount(DiscordSettingsSection, {
    global: { plugins: [createPinia()] },
    attachTo: document.body,
  })
}

function inputValue(wrapper: ReturnType<typeof mountSection>, id: string): string {
  return (wrapper.get(id).element as HTMLInputElement).value
}

function button(wrapper: ReturnType<typeof mountSection>, label: string) {
  return wrapper.findAll('button').find((node) => node.text() === label)!
}

describe('DiscordSettingsSection', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    getSettings.execute.mockResolvedValue(SETTINGS)
    provideDiscordUseCases({
      getSettings,
      saveSettings,
      testConnection,
      listChannels,
      previewMessage,
      sendMessage,
    })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('shows a skeleton until the settings load', async () => {
    const first = deferred<DiscordSettings>()
    getSettings.execute.mockReturnValue(first.promise)
    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('Loading Discord settings')

    first.resolve(SETTINGS)
    await flushPromises()

    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('shows an error with a retry when the settings fail to load', async () => {
    getSettings.execute.mockRejectedValueOnce(new Error('Scraper down'))
    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Scraper down')

    await button(wrapper, 'Try again').trigger('click')
    await flushPromises()

    expect(getSettings.execute).toHaveBeenCalledTimes(2)
    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('fills the form from the saved settings', async () => {
    const wrapper = mountSection()
    await flushPromises()

    expect(inputValue(wrapper, '#discord-default-channel')).toBe('12345678901234567')
    expect(inputValue(wrapper, '#discord-mention-user')).toBe('76543210987654321')
    expect(inputValue(wrapper, '#discord-template')).toBe('{title} at {company}')
    expect(inputValue(wrapper, '#discord-max-chars')).toBe('1900')
  })

  it('never shows the token and uses the hint as the placeholder', async () => {
    const wrapper = mountSection()
    await flushPromises()

    expect(inputValue(wrapper, '#discord-token')).toBe('')
    expect(wrapper.get('#discord-token').attributes('placeholder')).toBe('••••1234')
  })

  it('asks for a token when none is saved', async () => {
    getSettings.execute.mockResolvedValue({ ...SETTINGS, isConfigured: false, tokenHint: null })
    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.get('#discord-token').attributes('placeholder')).toBe('Bot token')
  })

  it('leaves the token out of the save when its box is empty', async () => {
    saveSettings.execute.mockResolvedValue(SETTINGS)
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-template').setValue('{title}')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveSettings.execute).toHaveBeenCalledTimes(1)
    const changes = saveSettings.execute.mock.calls[0]![0]
    expect(changes).not.toHaveProperty('token')
    expect(changes).toEqual({ messageTemplate: '{title}' })
  })

  it('sends only the token on a first save so the defaults stay out of the database', async () => {
    saveSettings.execute.mockResolvedValue(SETTINGS)
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-token').setValue('new.token')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveSettings.execute.mock.calls[0]![0]).toEqual({ token: 'new.token' })
  })

  it('sends a typed token', async () => {
    saveSettings.execute.mockResolvedValue(SETTINGS)
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('#discord-token').setValue('new.token')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveSettings.execute.mock.calls[0]![0].token).toBe('new.token')
  })

  it('sends null for a cleared channel and user id', async () => {
    saveSettings.execute.mockResolvedValue(SETTINGS)
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('#discord-default-channel').setValue('')
    await wrapper.get('#discord-mention-user').setValue('')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const changes = saveSettings.execute.mock.calls[0]![0]
    expect(changes.defaultChannelId).toBeNull()
    expect(changes.mentionUserId).toBeNull()
  })

  it('empties the token box and says saved after a save', async () => {
    saveSettings.execute.mockResolvedValue({ ...SETTINGS, tokenHint: '••••9999' })
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-token').setValue('new.token')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(inputValue(wrapper, '#discord-token')).toBe('')
    expect(wrapper.get('#discord-token').attributes('placeholder')).toBe('••••9999')
    expect(toastSuccess).toHaveBeenCalledWith('Discord settings saved')
  })

  it('shows the message when a save fails and keeps what was typed', async () => {
    saveSettings.execute.mockRejectedValue(new Error('Invalid channel id'))
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('#discord-token').setValue('new.token')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Invalid channel id')
    expect(inputValue(wrapper, '#discord-token')).toBe('new.token')
    expect(toastSuccess).not.toHaveBeenCalled()
  })

  it('turns Save into Saving and off while a save runs', async () => {
    const pending = deferred<DiscordSettings>()
    saveSettings.execute.mockReturnValue(pending.promise)
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('form').trigger('submit')

    expect(button(wrapper, 'Saving').attributes('disabled')).toBeDefined()

    pending.resolve(SETTINGS)
    await flushPromises()

    expect(button(wrapper, 'Save').attributes('disabled')).toBeUndefined()
  })

  it('tests the connection and shows the bot name', async () => {
    testConnection.execute.mockResolvedValue({ name: 'Jobs bot', id: '42' })
    const wrapper = mountSection()
    await flushPromises()

    await button(wrapper, 'Test connection').trigger('click')
    await flushPromises()

    expect(testConnection.execute).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[role="status"]').text()).toContain('Jobs bot')
    expect(saveSettings.execute).not.toHaveBeenCalled()
  })

  it('shows the message when the test fails', async () => {
    testConnection.execute.mockRejectedValue(new Error('Discord rejected the bot token.'))
    const wrapper = mountSection()
    await flushPromises()

    await button(wrapper, 'Test connection').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Discord rejected the bot token.')
  })

  it('turns the test button into Testing and off while it runs', async () => {
    const pending = deferred<{ name: string; id: string }>()
    testConnection.execute.mockReturnValue(pending.promise)
    const wrapper = mountSection()
    await flushPromises()

    await button(wrapper, 'Test connection').trigger('click')

    expect(button(wrapper, 'Testing').attributes('disabled')).toBeDefined()

    pending.resolve({ name: 'Jobs bot', id: '42' })
    await flushPromises()
  })

  it('keeps the test button off when no token is saved', async () => {
    getSettings.execute.mockResolvedValue({ ...SETTINGS, isConfigured: false, tokenHint: null })
    const wrapper = mountSection()
    await flushPromises()

    expect(button(wrapper, 'Test connection').attributes('disabled')).toBeDefined()
  })
})
