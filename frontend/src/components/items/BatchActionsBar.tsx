import { CheckCheck, X } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { itemsApi } from '../../api/items'

interface BatchActionsBarProps {
  /** 当前页可操作的 item id 列表 */
  itemIds: string[]
  /** 当前筛选下的总条目数 */
  total: number
}

export function BatchActionsBar({ itemIds, total }: BatchActionsBarProps) {
  const qc = useQueryClient()

  const markAllRead = useMutation({
    mutationFn: () => itemsApi.batchPatch(itemIds, { is_read: true }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['items'] })
      toast.success(`已标记 ${data.updated} 条为已读`)
    },
    onError: () => toast.error('操作失败'),
  })

  const markAllUnread = useMutation({
    mutationFn: () => itemsApi.batchPatch(itemIds, { is_read: false }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['items'] })
      toast.success(`已标记 ${data.updated} 条为未读`)
    },
    onError: () => toast.error('操作失败'),
  })

  if (itemIds.length === 0) return null

  const isPending = markAllRead.isPending || markAllUnread.isPending

  return (
    <div
      className="flex items-center gap-3 px-3 py-2 bg-primary-50 border border-primary-200 rounded-lg text-sm"
      role="status"
      aria-live="polite"
    >
      <span className="text-primary-700 font-medium">
        当前页 <b>{itemIds.length}</b> 条
        {total > itemIds.length && (
          <span className="text-gray-400 font-normal ml-1">（共 {total} 条）</span>
        )}
      </span>

      <div className="flex items-center gap-1.5 ml-auto">
        <button
          className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium
                     bg-white border border-gray-200 text-gray-600
                     hover:border-primary-400 hover:text-primary-600 transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed"
          onClick={() => markAllRead.mutate()}
          disabled={isPending}
          aria-busy={markAllRead.isPending}
        >
          <CheckCheck className="h-3.5 w-3.5" />
          全部已读
        </button>

        <button
          className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium
                     bg-white border border-gray-200 text-gray-500
                     hover:border-gray-400 hover:text-gray-700 transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed"
          onClick={() => markAllUnread.mutate()}
          disabled={isPending}
          aria-busy={markAllUnread.isPending}
        >
          <X className="h-3.5 w-3.5" />
          全部未读
        </button>
      </div>
    </div>
  )
}
