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
