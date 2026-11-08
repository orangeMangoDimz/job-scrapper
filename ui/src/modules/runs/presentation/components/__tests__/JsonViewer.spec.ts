import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import JsonViewer from '@/modules/runs/presentation/components/JsonViewer.vue'
import { MAX_HIGHLIGHT_CHARS, prettyJson } from '@/modules/runs/presentation/components/jsonTokens'

function mountViewer(value: Record<string, unknown>, jobCount?: number | null) {
  return mount(JsonViewer, { props: { value, jobCount }, attachTo: document.body })
}

function oversizedValue(): Record<string, unknown> {
  return { text: 'x'.repeat(MAX_HIGHLIGHT_CHARS), n: 1, flag: true }
}

function stubClipboard(writeText: (text: string) => Promise<void>) {
  vi.stubGlobal('navigator', { clipboard: { writeText } })
}

describe('JsonViewer', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('shows pretty printed json with two space indents', () => {
    const wrapper = mountViewer({ a: { b: 1 } })

    expect(wrapper.get('pre').text()).toBe('{\n  "a": {\n    "b": 1\n  }\n}')
  })

  it('colors keys, strings, numbers and literals with different classes', () => {
    const wrapper = mountViewer({ k: 's', n: 1, t: true, z: null })
    const classFor = (kind: string) => wrapper.get(`[data-token="${kind}"]`).classes().join(' ')

    const classes = ['key', 'string', 'number', 'literal'].map(classFor)

    expect(new Set(classes).size).toBe(4)
    expect(wrapper.get('[data-token="key"]').text()).toBe('"k"')
    expect(wrapper.get('[data-token="string"]').text()).toBe('"s"')
    expect(wrapper.get('[data-token="number"]').text()).toBe('1')
    expect(wrapper.findAll('[data-token="literal"]').map((node) => node.text())).toEqual([
      'true',
      'null',
    ])
  })

  it('escapes html like strings instead of rendering them', () => {
    const wrapper = mountViewer({ title: '<img src=x onerror=alert(1)><b>bold</b>' })

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('b').exists()).toBe(false)
    expect(wrapper.get('pre').text()).toContain('<img src=x onerror=alert(1)><b>bold</b>')
  })

  it('scrolls inside a box with a max height', () => {
    const wrapper = mountViewer({ a: 1 })

    expect(wrapper.get('[data-slot="json-scroll"]').classes().join(' ')).toMatch(/max-h-/)
    expect(wrapper.get('[data-slot="json-scroll"]').classes()).toContain('overflow-auto')
  })

  it('shows the job count it is given', () => {
    const wrapper = mountViewer({ a: 1 }, 12)

    expect(wrapper.get('[data-slot="json-count"]').text()).toBe('12 jobs')
  })

  it('says 1 job, not 1 jobs', () => {
    const wrapper = mountViewer({ a: 1 }, 1)

    expect(wrapper.text()).toContain('1 job')
    expect(wrapper.text()).not.toContain('1 jobs')
  })

  it('shows no count by itself, even when the value has count and jobs', () => {
    const wrapper = mountViewer({ count: 12, jobs: [{}] })

    expect(wrapper.find('[data-slot="json-count"]').exists()).toBe(false)
  })

  it('keeps the copy button on the right with and without a count', () => {
    const withCount = mountViewer({ a: 1 }, 2)
    const without = mountViewer({ a: 1 }, null)

    expect(withCount.get('[data-slot="json-copy"]').classes()).toContain('ml-auto')
    expect(without.get('[data-slot="json-copy"]').classes()).toContain('ml-auto')
    expect(without.find('span:empty').exists()).toBe(false)
  })

  it('colors every token while the text is within the limit', () => {
    const wrapper = mountViewer({ a: 'x'.repeat(100) })

    expect(wrapper.findAll('[data-token]').length).toBeGreaterThan(0)
  })

  it('shows big payloads as plain pretty text without one node per token', () => {
    const value = oversizedValue()
    const wrapper = mountViewer(value)

    expect(prettyJson(value).length).toBeGreaterThan(MAX_HIGHLIGHT_CHARS)
    expect(wrapper.find('[data-token]').exists()).toBe(false)
    expect(wrapper.findAll('pre span')).toHaveLength(0)
    expect(wrapper.get('pre').text()).toBe(prettyJson(value))
  })

  it('still copies the full pretty json for a big payload', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined)
    stubClipboard(writeText)
    const value = oversizedValue()
    const wrapper = mountViewer(value)

    await wrapper.get('button[data-slot="json-copy"]').trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith(prettyJson(value))
  })

  it('clears the Copied timer when it goes away', async () => {
    stubClipboard(vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined))
    const wrapper = mountViewer({ a: 1 })

    await wrapper.get('button[data-slot="json-copy"]').trigger('click')
    await flushPromises()
    expect(vi.getTimerCount()).toBe(1)

    wrapper.unmount()

    expect(vi.getTimerCount()).toBe(0)
  })

  it('copies the pretty json and shows Copied for a moment', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined)
    stubClipboard(writeText)
    const wrapper = mountViewer({ a: 1 })
    const button = wrapper.get('button[data-slot="json-copy"]')
    expect(button.text()).toBe('Copy')

    await button.trigger('click')
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith('{\n  "a": 1\n}')
    expect(button.text()).toBe('Copied')

    vi.advanceTimersByTime(2000)
    await flushPromises()

    expect(button.text()).toBe('Copy')
  })

  it('shows a failure message when the clipboard rejects', async () => {
    stubClipboard(vi.fn<(text: string) => Promise<void>>().mockRejectedValue(new Error('denied')))
    const wrapper = mountViewer({ a: 1 })
    const button = wrapper.get('button[data-slot="json-copy"]')

    await button.trigger('click')
    await flushPromises()

    expect(button.text()).toBe('Copy failed')
    expect(wrapper.get('[role="status"]').text()).toContain('Could not copy')
  })

  it('shows a failure message when there is no clipboard', async () => {
    vi.stubGlobal('navigator', {})
    const wrapper = mountViewer({ a: 1 })
    const button = wrapper.get('button[data-slot="json-copy"]')

    await button.trigger('click')
    await flushPromises()

    expect(button.text()).toBe('Copy failed')
  })
})
