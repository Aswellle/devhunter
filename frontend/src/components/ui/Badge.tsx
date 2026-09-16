import { clsx } from 'clsx'
import type { ReactNode } from 'react'

/* U2: Unified Badge component */

type BadgeColor = 'green' | 'red' | 'yellow' | 'primary' | 'gray'

export interface BadgeProps {
  color?: BadgeColor
  children: ReactNode
  className?: string
}

const colorClasses: Record<BadgeColor, string> = {
  green: 'badge-green',
  red: 'badge-red',
  yellow: 'badge-yellow',
  primary: 'badge-primary',
  gray: 'badge-gray',
}

export function Badge({ color = 'gray', children, className }: BadgeProps) {
  return (
    <span className={clsx('badge', colorClasses[color], className)}>
      {children}
    </span>
  )
}
