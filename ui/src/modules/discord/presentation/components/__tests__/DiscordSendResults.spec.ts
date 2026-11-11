import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import type { DiscordSendResult } from '@/modules/discord/domain/entities/Discord'
import DiscordSendResults from '@/modules/discord/presentation/components/DiscordSendResults.vue'

const RESULT: DiscordSendResult = {
  sent: 2,
  failed: 1,
  results: [
    { index: 0, kind: 'job', title: 'Dev', status: 'sent', messageId: '9', error: null },
    { index: 1, kind: 'job', title: null, status: 'failed', messageId: null, error: 'Too long' },
    { index: 2, kind: 'summary', title: null, status: 'sent', messageId: '10', error: null },
  ],
}

describe('DiscordSendResults', () => {
  it('shows the sent and failed counts', () => {
    const wrapper = mount(DiscordSendResults, { props: { result: RESULT } })

    expect(wrapper.text()).toContain('Sent 2, 1 failed')
  })

  it('lists every message with its status', () => {
    const wrapper = mount(DiscordSendResults, { props: { result: RESULT } })
    const rows = wrapper.findAll('li')

    expect(rows).toHaveLength(3)
    expect(rows[0]!.text()).toContain('Dev')
    expect(rows[0]!.get('[data-slot="badge"]').text()).toBe('Sent')
    expect(rows[0]!.get('[data-slot="badge"]').attributes('data-tone')).toBe('accent')
    expect(rows[1]!.get('[data-slot="badge"]').text()).toBe('Failed')
    expect(rows[1]!.get('[data-slot="badge"]').attributes('data-tone')).toBe('danger')
  })

  it('shows the reason a message failed', () => {
    const wrapper = mount(DiscordSendResults, { props: { result: RESULT } })

    expect(wrapper.findAll('li')[1]!.text()).toContain('Too long')
  })

  it('names messages with no title by their kind', () => {
    const wrapper = mount(DiscordSendResults, { props: { result: RESULT } })
    const rows = wrapper.findAll('li')

    expect(rows[1]!.text()).toContain('Job message 2')
    expect(rows[2]!.text()).toContain('Summary')
  })

  it('names a free text message Free text', () => {
    const wrapper = mount(DiscordSendResults, {
      props: {
        result: {
          sent: 1,
          failed: 0,
          results: [
            { index: 0, kind: 'text', title: null, status: 'sent', messageId: '1', error: null },
          ],
        },
      },
    })

    expect(wrapper.get('li').text()).toContain('Free text')
  })
})
