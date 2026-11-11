import { Play, Send, SlidersHorizontal } from '@lucide/vue'

import type { NavGroup } from '@/shared/components/types'

export const navGroups: NavGroup[] = [
  {
    id: 'scraper',
    label: 'Scraper',
    items: [
      { id: 'runs', label: 'Runs', icon: Play, to: '/runs' },
      { id: 'config', label: 'Config', icon: SlidersHorizontal, to: '/config' },
    ],
  },
  {
    id: 'discord',
    label: 'Discord',
    items: [{ id: 'discord', label: 'Discord', icon: Send, to: '/discord' }],
  },
]
