import type { Component } from 'vue'

export interface NavItem {
  id: string
  label: string
  icon: Component
  to: string
}

export interface NavGroup {
  id: string
  label?: string
  items: NavItem[]
}

export interface OutlineEntry {
  key: string
  label: string
  detail: string | null
}

export interface OutlineItem {
  key: string
  label: string
  badge: string | null
  isMuted?: boolean
  entries: readonly OutlineEntry[]
}
