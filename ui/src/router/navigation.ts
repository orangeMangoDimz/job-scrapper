import { Play, Send, SlidersHorizontal } from '@lucide/vue'

import type { NavItem } from '@/shared/components/types'

export const navItems: NavItem[] = [
  { id: 'runs', label: 'Runs', icon: Play, to: '/#runs' },
  { id: 'config', label: 'Config', icon: SlidersHorizontal, to: '/#config' },
  { id: 'discord', label: 'Discord', icon: Send, to: '/#discord' },
]
