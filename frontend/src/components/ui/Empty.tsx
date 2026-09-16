import { Inbox } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

interface EmptyProps {
  title: string
  description?: string
  action?: React.ReactNode
  icon?: LucideIcon
}

export function Empty({ title, description, action, icon: Icon }: EmptyProps) {
  const DisplayIcon = Icon || Inbox
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <DisplayIcon className="h-10 w-10 text-gray-300 mb-3" />
      <h3 className="text-base font-semibold text-gray-900">{title}</h3>
      {description && <p className="mt-1 text-sm text-gray-500 max-w-xs">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}