import { describe, expect, it } from 'vitest'
import { navGroups } from '@/router/navigation'

describe('navGroups', () => {
  it('puts a Discord group after the Scraper group', () => {
    expect(navGroups.map((group) => group.id)).toEqual(['scraper', 'discord'])
  })

  it('links the Discord group to the Discord page', () => {
    const group = navGroups.find((entry) => entry.id === 'discord')

    expect(group?.label).toBe('Discord')
    expect(group?.items).toEqual([
      expect.objectContaining({ id: 'discord', label: 'Discord', to: '/discord' }),
    ])
  })
})
