import { Inbox } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

interface EmptyProps {
  title: string
  description?: string
  action?: React.ReactNode
  icon?: LucideIcon
}

/* U7: role='status' 让屏幕阅读器识别为空状态提示 */
export function Empty({ title, description, action, icon: Icon }: EmptyProps) {
  const DisplayIcon = Icon || Inbox
  return (
    <section className="flex flex-col items-center justify-center py-16 text-center" role="status" aria-label={title}>
      <DisplayIcon className="h-10 w-10 text-gray-300 mb-3" aria-hidden="true" />
      <h3 className="text-base font-semibold text-gray-900">{title}</h3>
      {description && <p className="mt-1 text-sm text-gray-500 max-w-xs">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </section>
  )
}

