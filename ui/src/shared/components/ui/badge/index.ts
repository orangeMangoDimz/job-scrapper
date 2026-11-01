import type { VariantProps } from 'class-variance-authority'
import { cva } from 'class-variance-authority'

export { default as Badge } from './Badge.vue'

export const badgeVariants = cva(
  'inline-flex h-6 w-fit shrink-0 items-center gap-1 rounded-full border px-2.5 text-caption font-semibold whitespace-nowrap',
  {
    variants: {
      tone: {
        neutral: 'border-line bg-surface-subtle text-ink',
        accent: 'border-transparent bg-accent-soft text-accent',
        danger: 'border-transparent bg-danger-soft text-danger',
      },
    },
    defaultVariants: {
      tone: 'neutral',
    },
  },
)
export type BadgeVariants = VariantProps<typeof badgeVariants>

export const BADGE_ON_ACCENT_SOFT_CLASS = '[&_[data-slot=badge]:not([data-tone=danger])]:bg-surface'
