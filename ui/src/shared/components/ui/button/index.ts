import type { VariantProps } from 'class-variance-authority'
import { cva } from 'class-variance-authority'

export { default as Button } from './Button.vue'

export const buttonVariants = cva(
  'inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-full border border-transparent font-semibold whitespace-nowrap press outline-none select-none focus-visible:focus-ring disabled:cursor-not-allowed disabled:border-line disabled:bg-surface-subtle disabled:text-ink-muted [&_svg]:pointer-events-none [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-on-accent hover:bg-accent-hover',
        ink: 'bg-ink text-surface hover:bg-ink/85',
        secondary:
          'border-line-strong bg-surface text-ink hover:border-accent hover:bg-accent-soft hover:text-accent',
        ghost: 'bg-transparent text-ink hover:bg-accent-soft hover:text-accent',
        danger: 'bg-danger-soft text-danger hover:border-danger',
      },
      size: {
        md: 'h-10 px-5 text-body [&_svg:not([class*=size-])]:size-5',
        sm: 'h-8 px-4 text-body-sm [&_svg:not([class*=size-])]:size-4',
        icon: 'size-8 p-0 [&_svg:not([class*=size-])]:size-5',
        'icon-lg': 'size-10 p-0 [&_svg:not([class*=size-])]:size-5',
      },
    },
    compoundVariants: [
      {
        variant: 'ghost',
        size: ['icon', 'icon-lg'],
        class: 'hover:bg-surface-subtle hover:text-ink',
      },
    ],
    defaultVariants: {
      variant: 'secondary',
      size: 'md',
    },
  },
)
export type ButtonVariants = VariantProps<typeof buttonVariants>
