import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'

import type { LocationOption } from '@/modules/config/domain/entities/ScraperConfig'
import LocationPicker from '@/modules/config/presentation/components/LocationPicker.vue'

const OPTIONS: LocationOption[] = [
  { label: 'Jakarta', value: 'Jakarta Raya' },
  { label: 'Bandung', value: 'Bandung, Jawa Barat' },
  { label: 'Surabaya', value: 'Surabaya, Jawa Timur' },
]

function stubBrowser(): void {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn<ResizeObserver['observe']>()
      unobserve = vi.fn<ResizeObserver['unobserve']>()
      disconnect = vi.fn<ResizeObserver['disconnect']>()
    },
  )
  Element.prototype.scrollIntoView = vi.fn()
}

type PickerWrapper = VueWrapper<InstanceType<typeof LocationPicker>>

const mounted: PickerWrapper[] = []

function mountPicker(modelValue: string[]): PickerWrapper {
  const wrapper = mount(LocationPicker, {
    props: { id: 'glints-locations', modelValue, options: OPTIONS },
    attachTo: document.body,
  })
  mounted.push(wrapper)
  return wrapper
}

function lastUpdate(wrapper: PickerWrapper): string[] | undefined {
  const updates = wrapper.emitted('update:modelValue') ?? []
  return updates[updates.length - 1]?.[0] as string[] | undefined
}

function updates(wrapper: PickerWrapper): string[][] {
  return (wrapper.emitted('update:modelValue') ?? []).map((args) => args[0] as string[])
}

function chips(): HTMLElement[] {
  return Array.from(document.body.querySelectorAll<HTMLElement>('[data-slot="tags-input-item"]'))
}

function optionLabels(): string[] {
  const options = document.body.querySelectorAll('[role="option"]')
  return Array.from(options).map((option) => option.textContent?.trim() ?? '')
}

async function openList(wrapper: PickerWrapper): Promise<void> {
  const input = wrapper.get('#glints-locations')
  await input.trigger('focus')
  await input.trigger('click')
  await flushPromises()
}

describe('LocationPicker', () => {
  beforeEach(stubBrowser)

  afterEach(() => {
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('shows the pick placeholder while no city is picked', () => {
    const wrapper = mountPicker([])

    expect(wrapper.get('#glints-locations').attributes('placeholder')).toBe('Pick cities')
    expect(chips()).toHaveLength(0)
  })

  it('shows a chip with the clean label for each known value', () => {
    mountPicker(['Jakarta Raya', 'Bandung, Jawa Barat'])

    expect(chips().map((chip) => chip.textContent?.trim())).toEqual(['Jakarta', 'Bandung'])
    expect(chips().every((chip) => chip.dataset.unknown === undefined)).toBe(true)
  })

  it('keeps a saved value that is not in the list as a marked chip', () => {
    mountPicker(['Jakarta Raya', 'Atlantis'])

    const [, unknown] = chips()
    expect(unknown?.textContent).toContain('Atlantis')
    expect(unknown?.dataset.unknown).toBe('true')
    expect(unknown?.getAttribute('title')).toBe('Not in the city list')
  })

  it('adds the raw value when a city is chosen from the list', async () => {
    const wrapper = mountPicker(['Jakarta Raya'])

    await openList(wrapper)
    const bandung = Array.from(document.body.querySelectorAll('[role="option"]')).find((option) =>
      option.textContent?.includes('Bandung'),
    )
    bandung?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()

    expect(lastUpdate(wrapper)).toEqual(['Jakarta Raya', 'Bandung, Jawa Barat'])
  })

  it('marks the picked cities in the list', async () => {
    const wrapper = mountPicker(['Jakarta Raya'])

    await openList(wrapper)

    const selected = document.body.querySelectorAll('[role="option"][data-state="checked"]')
    expect(Array.from(selected).map((option) => option.textContent?.trim())).toEqual(['Jakarta'])
  })

  it('removes a city from the picked ones with its chip button', async () => {
    const wrapper = mountPicker(['Jakarta Raya', 'Bandung, Jawa Barat'])

    const remove = chips()[0]?.querySelector<HTMLElement>('[data-slot="tags-input-item-delete"]')
    remove?.click()
    await flushPromises()

    expect(lastUpdate(wrapper)).toEqual(['Bandung, Jawa Barat'])
  })

  it('removes a saved value that is not in the list', async () => {
    const wrapper = mountPicker(['Atlantis'])

    const remove = chips()[0]?.querySelector<HTMLElement>('[data-slot="tags-input-item-delete"]')
    remove?.click()
    await flushPromises()

    expect(lastUpdate(wrapper)).toEqual([])
  })

  it('filters the list by label while typing', async () => {
    const wrapper = mountPicker([])

    await openList(wrapper)
    expect(optionLabels()).toEqual(['Jakarta', 'Bandung', 'Surabaya'])
    await wrapper.get('#glints-locations').setValue('bAnd')
    await flushPromises()

    expect(optionLabels()).toEqual(['Bandung'])
  })

  it('does not accept a typed value that is not in the list', async () => {
    const wrapper = mountPicker([])

    await openList(wrapper)
    const input = wrapper.get('#glints-locations')
    await input.setValue('Atlantis')
    await input.trigger('keydown', { key: 'Enter' })
    const field = input.element as HTMLInputElement
    field.value = 'Atlantis,'
    field.dispatchEvent(new InputEvent('input', { data: ',', bubbles: true }))
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(document.body.textContent).toContain('No city found')
  })

  it('emits exactly once with the new list when a city is chosen', async () => {
    const wrapper = mountPicker(['Jakarta Raya'])

    await openList(wrapper)
    const bandung = Array.from(document.body.querySelectorAll('[role="option"]')).find((option) =>
      option.textContent?.includes('Bandung'),
    )
    bandung?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()

    expect(updates(wrapper)).toEqual([['Jakarta Raya', 'Bandung, Jawa Barat']])
  })

  it('emits exactly once with the shorter list when a chip is removed', async () => {
    const wrapper = mountPicker(['Jakarta Raya', 'Bandung, Jawa Barat'])

    chips()[0]?.querySelector<HTMLElement>('[data-slot="tags-input-item-delete"]')?.click()
    await flushPromises()

    expect(updates(wrapper)).toEqual([['Bandung, Jawa Barat']])
  })

  it('emits exactly once when a picked city is chosen again to unpick it', async () => {
    const wrapper = mountPicker(['Jakarta Raya', 'Bandung, Jawa Barat'])

    await openList(wrapper)
    const jakarta = Array.from(document.body.querySelectorAll('[role="option"]')).find((option) =>
      option.textContent?.includes('Jakarta'),
    )
    jakarta?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()

    expect(updates(wrapper)).toEqual([['Bandung, Jawa Barat']])
  })

  it('does not add a typed value on paste', async () => {
    const wrapper = mountPicker([])

    await openList(wrapper)
    const input = wrapper.get('#glints-locations')
    await input.setValue('Atlantis')
    const paste = new Event('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(paste, 'clipboardData', {
      value: { getData: () => 'Atlantis' },
    })
    input.element.dispatchEvent(paste)
    await flushPromises()

    expect(updates(wrapper)).toEqual([])
    expect(chips()).toHaveLength(0)
  })

  it('does not add a typed value on blur', async () => {
    const wrapper = mountPicker([])

    await openList(wrapper)
    const input = wrapper.get('#glints-locations')
    await input.setValue('Atlantis')
    await input.trigger('blur')
    await flushPromises()

    expect(updates(wrapper)).toEqual([])
    expect(chips()).toHaveLength(0)
  })

  it('does not add a typed value on Tab', async () => {
    const wrapper = mountPicker([])

    await openList(wrapper)
    const input = wrapper.get('#glints-locations')
    await input.setValue('Atlantis')
    await input.trigger('keydown', { key: 'Tab' })
    await flushPromises()

    expect(updates(wrapper)).toEqual([])
    expect(chips()).toHaveLength(0)
  })
})
