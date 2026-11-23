import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Info, Sparkles, ThumbsUp, X } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { userPrefsApi } from '../../api/user_prefs'
import { queryKeys } from '../../api/queryKeys'
import { formatDistanceToNow } from '../../utils/time'
import { RECOMMENDED_BADGE_SCORE } from '../../utils/scores'
import { isSafeExternalUrl } from '../../utils/url'
import { ReasonBadges } from '../recommend/ReasonBadges'
import { ScorePill } from '../ui/ScorePill'
import { Spinner } from '../ui/Spinner'
import type { RecommendedItem } from '../../types'

interface ForYouSectionProps {
  onOpenPreferences: () => void
}

export function ForYouSection({ onOpenPreferences }: ForYouSectionProps) {
  const { data, isLoading, isError, refetch, failureCount } = useQuery({
    queryKey: queryKeys.recommendations.home(),
    queryFn: () => userPrefsApi.getRecommendations({ limit: 10, exclude_read: true }),
    staleTime: 30_000,  // 30秒内不重新请求
  })

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-4 w-4 text-primary-500" />
          <h2 className="text-sm font-semibold text-gray-700">为你推荐</h2>
          {/* 数字含义说明：裸数字（如 20）此前没有任何可读标签 */}
          <span
            className="inline-flex items-center gap-1 text-xs text-gray-400 cursor-help"
            title="推荐分（0–100）＝ 兴趣匹配、阅读亲缘、新鲜度、参与度、探索度 五项因子的加权平均。权重可在「偏好设置」中调整。"
          >
            <Info className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="sr-only">
              推荐分为 0 到 100，由兴趣匹配、阅读亲缘、新鲜度、参与度、探索度加权得出
            </span>
          </span>
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
  const qc = useQueryClient()
  const score = Math.round(item.recommendation_score * 100)
  // 爬取内容的外链只放行 http(s)，防 javascript:/data: URL（纵深防御，后端已有校验）
  const safeHref = isSafeExternalUrl(item.url) ? item.url : undefined

  const recordClick = () => {
    userPrefsApi
      .recordInteraction({ item_id: item.id, interaction_type: 'click' })
      .catch(() => {})
  }

  // 不感兴趣：写入负反馈，推荐引擎会永久排除该条目并立即刷新列表。
  // 此前负反馈接口与数据表都存在，但引擎从不读取、UI 也没有入口——
  // 用户没有任何负向调节手段，"精准推荐"缺少最关键的一路信号。
  const dismissMutation = useMutation({
    mutationFn: () =>
      userPrefsApi.recordFeedback({ item_id: item.id, feedback_type: 'not_interested' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.recommendations.all })
      toast.success('已隐藏，这条内容不会再出现在推荐里')
    },
    onError: () => toast.error('操作失败，请重试'),
  })

  return (
    <div className="group flex items-start gap-2 p-2 rounded-lg hover:bg-gray-50 transition-colors">
      {/* 推荐分：带标签与分项说明（非 compact——裸数字无法自解释） */}
      <div className="shrink-0 mt-0.5">
        <ScorePill
          score={score}
          title="推荐分（0–100）：兴趣匹配、阅读亲缘、新鲜度、参与度、探索度的加权平均"
        />
      </div>

      {/* 内容 */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-1">
          <h3 className="text-sm font-medium text-gray-800 leading-snug line-clamp-2 group-hover:text-primary-600 transition-colors">
            <a
              href={safeHref}
              target={safeHref ? '_blank' : undefined}
              rel="noopener noreferrer"
              className="hover:text-primary-600"
              onClick={recordClick}
            >
              {item.title}
            </a>
          </h3>
          {/* 快捷打开原文：常驻按钮（此前只有标题内嵌的悬停图标） */}
          {safeHref ? (
            <a
              href={safeHref}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => {
                e.stopPropagation()
                recordClick()
              }}
              title="打开原文"
              aria-label={`打开原文：${item.title}`}
              className="shrink-0 inline-flex items-center gap-1 px-1.5 py-1 rounded-md text-gray-400
                         hover:text-primary-600 hover:bg-primary-50 transition-colors
                         focus-visible:ring-2 focus-visible:ring-primary-500 outline-none"
            >
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="text-[11px] hidden sm:inline">打开</span>
            </a>
          ) : (
            <span
              className="shrink-0 p-1 text-gray-200 cursor-not-allowed"
              title="该条目的链接不可访问（非 http/https）"
            >
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </span>
          )}
          {/* 不感兴趣：永久排除该条目（负反馈） */}
          <button
            type="button"
            onClick={() => dismissMutation.mutate()}
            disabled={dismissMutation.isPending}
            title="不感兴趣：不再推荐这条内容"
            aria-label={`不感兴趣：${item.title}`}
            className="shrink-0 p-1 rounded-md text-gray-300 hover:text-red-500 hover:bg-red-50
                       transition-colors disabled:opacity-40
                       focus-visible:ring-2 focus-visible:ring-red-400 outline-none"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          {item.task_name && (
            <span className="text-xs text-gray-400">{item.task_name}</span>
          )}
          <span className="text-xs text-gray-300">·</span>
          <span className="text-xs text-gray-400">
            {formatDistanceToNow(item.fetched_at)}
          </span>
          {score >= RECOMMENDED_BADGE_SCORE && (
            <>
              <span className="text-xs text-gray-300">·</span>
              <span className="text-xs text-primary-500 font-medium flex items-center gap-0.5">
                <ThumbsUp className="h-2.5 w-2.5" />
                强推
              </span>
            </>
          )}
        </div>
        <ReasonBadges reasons={item.recommendation_reasons} max={2} />
      </div>
    </div>
  )
}
