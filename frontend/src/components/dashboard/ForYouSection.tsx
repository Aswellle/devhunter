import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Sparkles, ThumbsUp } from 'lucide-react'
import { userPrefsApi } from '../../api/user_prefs'
import { formatDistanceToNow } from '../../utils/time'
import { Spinner } from '../ui/Spinner'
import type { RecommendedItem } from '../../types'

interface ForYouSectionProps {
  onOpenPreferences: () => void
}

export function ForYouSection({ onOpenPreferences }: ForYouSectionProps) {
  const { data, isLoading, isError, refetch, failureCount } = useQuery({
    queryKey: ['recommendations'],
    queryFn: () => userPrefsApi.getRecommendations({ limit: 10, exclude_read: true }),
    staleTime: 30_000,  // 30秒内不重新请求
  })

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-4 w-4 text-primary-500" />
          <h2 className="text-sm font-semibold text-gray-700">为你推荐</h2>
        </div>
        <button
          onClick={onOpenPreferences}
          className="text-xs text-gray-500 hover:text-gray-700"
        >
          偏好设置
        </button>
      </div>

      {isLoading ? (
        <div className="py-8 flex justify-center" role="status" aria-label="加载推荐中">
          <Spinner />
        </div>
      ) : isError ? (
        <div className="py-6 text-center" role="alert">
          <p className="text-sm text-danger mb-2">推荐加载失败</p>
          <button onClick={() => refetch()} className="btn-ghost text-xs py-1">
            重试 {failureCount > 0 && `(${failureCount})`}
          </button>
        </div>
      ) : !data?.items.length ? (
        <div className="py-6 text-center">
          <ThumbsUp className="h-8 w-8 text-gray-300 mx-auto mb-2" />
          <p className="text-sm text-gray-500">暂无推荐内容</p>
          <p className="text-xs text-gray-400 mt-1">
            点击「偏好设置」配置你的兴趣方向
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {data.items.slice(0, 5).map((item) => (
            <ForYouItemCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  )
}

function ForYouItemCard({ item }: { item: RecommendedItem }) {
  const score = Math.round(item.recommendation_score * 100)

  return (
    <div className="group flex items-start gap-2 p-2 rounded-lg hover:bg-gray-50 transition-colors">
      {/* 得分指示 */}
      <div className="shrink-0 w-8 h-8 rounded-md bg-primary-50 flex flex-col items-center justify-center">
        <span className="text-[10px] text-primary-500 font-medium">{score}%</span>
      </div>

      {/* 内容 */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-1">
          <h3 className="text-sm font-medium text-gray-800 leading-snug line-clamp-2 group-hover:text-primary-600 transition-colors">
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary-600"
              onClick={() => {
                // 记录点击交互
                userPrefsApi.recordInteraction({
                  item_id: item.id,
                  interaction_type: 'click',
                })
              }}
            >
              {item.title}
              <ExternalLink className="h-3 w-3 inline ml-1 opacity-0 group-hover:opacity-50 transition-opacity" />
            </a>
          </h3>
        </div>
        <div className="flex items-center gap-2 mt-1">
          {item.task_name && (
            <span className="text-xs text-gray-400">{item.task_name}</span>
          )}
          <span className="text-xs text-gray-300">·</span>
          <span className="text-xs text-gray-400">
            {formatDistanceToNow(item.fetched_at)}
          </span>
          {score >= 70 && (
            <>
              <span className="text-xs text-gray-300">·</span>
              <span className="text-xs text-primary-500 font-medium flex items-center gap-0.5">
                <ThumbsUp className="h-2.5 w-2.5" />
                推荐
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
