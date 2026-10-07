import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Star } from 'lucide-react'
import { clsx } from 'clsx'
import { toast } from 'react-hot-toast'
import type { Item } from '../../types'
import { itemsApi } from '../../api/items'
import { queryKeys } from '../../api/queryKeys'
import { userPrefsApi } from '../../api/user_prefs'
import { formatDistanceToNow } from '../../utils/time'
import { ClampText } from '../ui/ClampText'

interface ItemCardProps {
  item: Item
}

export function ItemCard({ item }: ItemCardProps) {
  const qc = useQueryClient()

  const handleTitleClick = () => {
    // 记录点击交互（fire-and-forget，失败静默）
    userPrefsApi
      .recordInteraction({ item_id: item.id, interaction_type: 'click' })
      .catch(() => {})
    if (!item.is_read) {
      itemsApi
        .patch(item.id, { is_read: true })
        .then(() => {
          // 记录阅读（已读）交互
          return userPrefsApi.recordInteraction({ item_id: item.id, interaction_type: 'view' })
        })
        .catch(() => {})
      // 未读状态的变化需要反映到列表缓存；stats/推荐由列表页的 onSettled 兜底
      qc.invalidateQueries({ queryKey: queryKeys.items.all })
    }
  }

  const starMutation = useMutation({
    mutationFn: ({ starred }: { starred: boolean }) =>
      itemsApi.patch(item.id, { is_starred: starred }),
    onSuccess: (_, { starred }) => {
      // 记录收藏交互
      userPrefsApi
        .recordInteraction({ item_id: item.id, interaction_type: starred ? 'star' : 'click' })
        .catch(() => {})
      qc.invalidateQueries({ queryKey: queryKeys.items.all })
      qc.invalidateQueries({ queryKey: queryKeys.items.starredAll })
      qc.invalidateQueries({ queryKey: queryKeys.recommendations.all })
      toast.success(starred ? '已收藏' : '已取消收藏')
    },
    onError: () => {
      toast.error('操作失败，请重试')
    },
  })

  return (
    <div
      className={clsx(
        'card p-4 transition-all hover:shadow-md',
        !item.is_read && 'border-l-4 border-l-primary-500'
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {/* 标题 */}
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={handleTitleClick}
            className={clsx(
              'flex items-center gap-1.5 text-sm font-medium hover:text-primary-600 transition-colors group',
              item.is_read ? 'text-gray-500' : 'text-gray-900'
            )}
          >
            {/* U7: unread state was previously conveyed only by the card's
                left border color — invisible to colorblind users and easy
                to miss at a glance. This dot + sr-only label give it a
                shape/text channel independent of color. */}
            {!item.is_read && (
              <span
                className="inline-block h-1.5 w-1.5 rounded-full bg-primary-500 shrink-0"
                aria-hidden="true"
              />
            )}
            <span className="sr-only">{item.is_read ? '已读' : '未读'}</span>
            <span className="line-clamp-2">{item.title}</span>
            <ExternalLink className="h-3 w-3 shrink-0 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100" />
          </a>

          {/* 摘要 */}
          <ClampText text={item.summary} className="mt-1 text-xs text-gray-500" />

          {/* meta */}
          <div className="mt-2 flex items-center gap-3 text-xs text-gray-400">
            {item.task_name && (
              <span className="badge badge-gray">{item.task_name}</span>
            )}
            <span>{formatDistanceToNow(item.fetched_at)}</span>
          </div>
        </div>

        {/* Star 按钮 */}
        <button
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            starMutation.mutate({ starred: !item.is_starred })
          }}
          disabled={starMutation.isPending}
          aria-busy={starMutation.isPending}
          aria-pressed={item.is_starred}
          aria-label={item.is_starred ? '取消收藏' : '收藏'}
          className={clsx(
            'p-2 -m-1 rounded transition-colors shrink-0 disabled:opacity-50',
            item.is_starred
              ? 'text-yellow-500 hover:text-yellow-600'
              : 'text-gray-300 hover:text-yellow-400'
          )}
        >
          <Star className="h-4 w-4" fill={item.is_starred ? 'currentColor' : 'none'} />
        </button>
      </div>
    </div>
  )
}
