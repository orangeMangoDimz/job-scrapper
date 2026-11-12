import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createMemoryStorage } from '@/__tests__/memoryStorage'
import type { RunDetail, RunPayload } from '@/modules/runs/domain/entities/Run'
import RunResults from '@/modules/runs/presentation/components/RunResults.vue'
import { RESULTS_TAB_STORAGE_KEY } from '@/modules/runs/presentation/components/resultsTabStorage'

const PAYLOADS: RunPayload[] = [
  {
    keyword: 'AI Engineering',
    site: 'jobstreet',
    raw: { source: 'raw-jobstreet-ai', items: [1, 2, 3] },
    filtered: { source: 'filtered-jobstreet-ai', count: 2, jobs: [{}, {}] },
  },
  {
    keyword: 'Vue',
    site: 'indeed',
    raw: { source: 'raw-indeed-vue' },
    filtered: null,
  },
]

function makeDetail(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    record: {
      id: 'run-1',
      status: 'succeeded',
      keywords: ['AI Engineering', 'Vue'],
      sites: ['jobstreet', 'indeed'],
      startedAt: '2026-11-01T10:00:00+00:00',
      finishedAt: '2026-11-01T10:01:00+00:00',
      jobCount: 1,
      errorCount: 0,
      error: null,
      discordStatus: null,
      discordSent: 0,
      discordFailed: 0,
      discordError: null,
    },
    jobs: [
      {
        site: 'jobstreet',
        matchedKeyword: 'AI Engineering',
        title: 'ML Engineer',
        company: 'Acme',
        location: 'Remote',
        url: 'https://example.com/1',
        postedAt: null,
      },
    ],
    failures: [],
    payloads: PAYLOADS,
    ...overrides,
  }
}

function mountResults(detail: RunDetail = makeDetail()) {
  return mount(RunResults, { props: { detail }, attachTo: document.body })
}

type Wrapper = ReturnType<typeof mountResults>

function tab(wrapper: Wrapper, name: string) {
  const found = wrapper.findAll('[role="tab"]').find((node) => node.text() === name)
  if (found === undefined) {
    throw new Error(`No tab named ${name}`)
  }
  return found
}

async function openTab(wrapper: Wrapper, name: string) {
  await tab(wrapper, name).trigger('mousedown', { button: 0, ctrlKey: false })
  await nextTick()
}

function chips(wrapper: Wrapper) {
  return wrapper.findAll('[data-slot="payload-chip"]')
}

async function pickChip(wrapper: Wrapper, label: string) {
  const chip = chips(wrapper).find((node) => node.text() === label)
  if (chip === undefined) {
    throw new Error(`No chip named ${label}`)
  }
  await chip.trigger('click')
}

describe('RunResults', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createMemoryStorage())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('has a tab bar with Cards, Raw JSON and Filtered JSON', () => {
    const wrapper = mountResults()

    expect(wrapper.findAll('[role="tab"]').map((node) => node.text())).toEqual([
      'Cards',
      'Raw JSON',
      'Filtered JSON',
    ])
  })

  it('starts on Cards the first time and shows the job cards', () => {
    const wrapper = mountResults()

    expect(tab(wrapper, 'Cards').attributes('aria-selected')).toBe('true')
    expect(wrapper.text()).toContain('ML Engineer')
    expect(wrapper.find('[data-slot="payload-chip"]').exists()).toBe(false)
  })

  it('shows the empty state for no jobs under Cards', () => {
    const wrapper = mountResults(makeDetail({ jobs: [] }))

    expect(wrapper.text()).toContain('No jobs found.')
  })

  it('keeps the run error and failures above the tabs', async () => {
    const wrapper = mountResults(
      makeDetail({
        failures: [{ keyword: 'Vue', site: 'indeed', reason: 'timeout' }],
        record: { ...makeDetail().record, error: 'Boom' },
      }),
    )
    await openTab(wrapper, 'Raw JSON')

    expect(wrapper.get('[role="alert"]').text()).toContain('Boom')
    expect(wrapper.get('[aria-label="Failed searches"]').text()).toContain('timeout')
  })

  it('shows the raw json of the first file under Raw JSON', async () => {
    const wrapper = mountResults()
    await openTab(wrapper, 'Raw JSON')

    expect(wrapper.get('pre').text()).toContain('raw-jobstreet-ai')
    expect(wrapper.text()).not.toContain('ML Engineer')
  })

  it('shows the filtered json under Filtered JSON', async () => {
    const wrapper = mountResults()
    await openTab(wrapper, 'Filtered JSON')

    expect(wrapper.get('pre').text()).toContain('filtered-jobstreet-ai')
    expect(wrapper.text()).toContain('2 jobs')
  })

  it('labels the site chips with site and keyword and picks the first by default', async () => {
    const wrapper = mountResults()
    await openTab(wrapper, 'Raw JSON')

    expect(chips(wrapper).map((node) => node.text())).toEqual([
      'jobstreet · AI Engineering',
      'indeed · Vue',
    ])
    expect(chips(wrapper).map((node) => node.attributes('aria-pressed'))).toEqual(['true', 'false'])
  })

  it('switches the shown file when another chip is picked', async () => {
    const wrapper = mountResults()
    await openTab(wrapper, 'Raw JSON')

    await pickChip(wrapper, 'indeed · Vue')

    expect(wrapper.get('pre').text()).toContain('raw-indeed-vue')
    expect(wrapper.get('pre').text()).not.toContain('raw-jobstreet-ai')
  })

  it('keeps the picked file when flipping between Raw and Filtered', async () => {
    const payloads: RunPayload[] = [
      PAYLOADS[0]!,
      { ...PAYLOADS[1]!, filtered: { source: 'filtered-indeed-vue', count: 0 } },
    ]
    const wrapper = mountResults(makeDetail({ payloads }))
    await openTab(wrapper, 'Raw JSON')
    await pickChip(wrapper, 'indeed · Vue')

    await openTab(wrapper, 'Filtered JSON')

    expect(wrapper.get('pre').text()).toContain('filtered-indeed-vue')
    expect(
      chips(wrapper)
        .find((node) => node.text() === 'indeed · Vue')
        ?.attributes('aria-pressed'),
    ).toBe('true')

    await openTab(wrapper, 'Raw JSON')

    expect(wrapper.get('pre').text()).toContain('raw-indeed-vue')
  })

  it('goes back to the first file when another run is shown', async () => {
    const wrapper = mountResults()
    await openTab(wrapper, 'Raw JSON')
    await pickChip(wrapper, 'indeed · Vue')

    await wrapper.setProps({
      detail: makeDetail({ record: { ...makeDetail().record, id: 'run-2' } }),
    })

    expect(wrapper.get('pre').text()).toContain('raw-jobstreet-ai')
  })

  it('falls back to the first file when the picked one is gone from the same run', async () => {
    const wrapper = mountResults()
    await openTab(wrapper, 'Raw JSON')
    await pickChip(wrapper, 'indeed · Vue')

    await wrapper.setProps({ detail: makeDetail({ payloads: [PAYLOADS[0]!] }) })

    expect(wrapper.get('pre').text()).toContain('raw-jobstreet-ai')
    expect(wrapper.text()).not.toContain('Raw data was not saved for this run')
    expect(chips(wrapper).map((node) => node.attributes('aria-pressed'))).toEqual(['true'])
  })

  it('shows the raw and filtered panels from the same tab list', async () => {
    const wrapper = mountResults()

    await openTab(wrapper, 'Raw JSON')
    expect(wrapper.findAll('[role="tabpanel"][data-state="active"] pre')).toHaveLength(1)
    await openTab(wrapper, 'Filtered JSON')

    expect(wrapper.findAll('[role="tabpanel"][data-state="active"] pre')).toHaveLength(1)
    expect(wrapper.get('pre').text()).toContain('filtered-jobstreet-ai')
  })

  it('says raw data was not saved when the run has no payloads', async () => {
    const wrapper = mountResults(makeDetail({ payloads: [] }))
    await openTab(wrapper, 'Raw JSON')

    expect(wrapper.text()).toContain('Raw data was not saved for this run')
    expect(wrapper.find('pre').exists()).toBe(false)
    expect(wrapper.find('[data-slot="payload-chip"]').exists()).toBe(false)
  })

  it('says filtered data was not saved when the run has no payloads', async () => {
    const wrapper = mountResults(makeDetail({ payloads: [] }))
    await openTab(wrapper, 'Filtered JSON')

    expect(wrapper.text()).toContain('Filtered data was not saved for this run')
    expect(wrapper.find('pre').exists()).toBe(false)
  })

  it('says filtered data was not saved when only the picked filtered file is null', async () => {
    const wrapper = mountResults()
    await openTab(wrapper, 'Filtered JSON')
    await pickChip(wrapper, 'indeed · Vue')

    expect(wrapper.text()).toContain('Filtered data was not saved for this run')
    expect(wrapper.find('pre').exists()).toBe(false)
    expect(chips(wrapper)).toHaveLength(2)
  })

  it('says raw data was not saved when the picked raw file is null', async () => {
    const payloads: RunPayload[] = [{ ...PAYLOADS[0]!, raw: null }]
    const wrapper = mountResults(makeDetail({ payloads }))
    await openTab(wrapper, 'Raw JSON')

    expect(wrapper.text()).toContain('Raw data was not saved for this run')
    expect(wrapper.find('pre').exists()).toBe(false)
  })

  it('remembers the last used tab', async () => {
    const first = mountResults()
    await openTab(first, 'Filtered JSON')

    expect(window.localStorage.getItem(RESULTS_TAB_STORAGE_KEY)).toBe('filtered')
    first.unmount()

    const second = mountResults()

    expect(tab(second, 'Filtered JSON').attributes('aria-selected')).toBe('true')
    expect(second.get('pre').text()).toContain('filtered-jobstreet-ai')
  })

  it('falls back to Cards when the stored tab is unknown', () => {
    window.localStorage.setItem(RESULTS_TAB_STORAGE_KEY, 'xml')

    expect(tab(mountResults(), 'Cards').attributes('aria-selected')).toBe('true')
  })

  it('still works when storage throws on read and write', async () => {
    vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const wrapper = mountResults()

    expect(tab(wrapper, 'Cards').attributes('aria-selected')).toBe('true')

    await openTab(wrapper, 'Raw JSON')

    expect(tab(wrapper, 'Raw JSON').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('pre').text()).toContain('raw-jobstreet-ai')
  })

  it('opens a tab when it gets keyboard focus', async () => {
    const wrapper = mountResults()

    ;(tab(wrapper, 'Raw JSON').element as HTMLElement).focus()
    await flushPromises()

    expect(tab(wrapper, 'Raw JSON').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('pre').text()).toContain('raw-jobstreet-ai')
  })

  describe('discord status', () => {
    function withDiscord(overrides: Partial<RunDetail['record']>): RunDetail {
      const detail = makeDetail()
      return { ...detail, record: { ...detail.record, ...overrides } }
    }

    it('shows nothing about Discord when there was no send', () => {
      const wrapper = mountResults()

      expect(wrapper.find('[data-slot="discord-status"]').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('Discord')
    })

    it.each<[Partial<RunDetail['record']>, string, string]>([
      [{ discordStatus: 'sending' }, 'Sending to Discord', 'neutral'],
      [{ discordStatus: 'sent', discordSent: 3 }, 'Sent 3 to Discord', 'accent'],
      [
        { discordStatus: 'partial', discordSent: 2, discordFailed: 1 },
        'Sent 2, failed 1 on Discord',
        'neutral',
      ],
      [
        { discordStatus: 'failed', discordError: 'Missing access' },
        'Discord failed: Missing access',
        'danger',
      ],
    ])('shows the send status for %o', (overrides, label, tone) => {
      const wrapper = mountResults(withDiscord(overrides))
      const status = wrapper.get('[data-slot="discord-status"]')

      expect(status.text()).toBe(label)
      expect(status.attributes('data-tone')).toBe(tone)
    })
  })
})
