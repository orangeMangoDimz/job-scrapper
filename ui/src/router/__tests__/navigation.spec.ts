import { describe, expect, it } from 'vitest'
import { navItems } from '@/router/navigation'

describe('navItems', () => {
  it('links Runs, Config and Discord to their sections on the single page', () => {
    expect(navItems.map(({ label, to }) => ({ label, to }))).toEqual([
      { label: 'Runs', to: '/#runs' },
      { label: 'Config', to: '/#config' },
      { label: 'Discord', to: '/#discord' },
    ])
  })
})
