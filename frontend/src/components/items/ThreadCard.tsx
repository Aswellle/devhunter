import { useState } from 'react'
import { ChevronDown, ChevronRight, ExternalLink, Flame, Gauge, Globe, Star, Rss, TrendingUp } from 'lucide-react'
import { clsx } from 'clsx'
import { useQuery } from '@tanstack/react-query'
import type { Thread, ThreadStats } from '../../types'
import { formatDistanceToNow } from '../../utils/time'
import { queryKeys } from '../../api/queryKeys'
import { threadsApi } from '../../api/threads'
import { ClampText } from '../ui/ClampText'
import { deriveThreadStatus, THREAD_STATUS_META } from '../../utils/threadStatus'

// Platform display name mapping
const PLATFORM_NAMES: Record<string, string> = {
  hackernews: 'HN',
  v2ex: 'V2EX',
  github_trending: 'GitHub',
  juejin: '掘金',
  indiehackers: 'IH',
}

function PlatformBadge({ name }: { name: string }) {
  const label = PLATFORM_NAMES[name] ?? name
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
      <Rss className="h-3 w-3" />
      {label}
    </span>
  )
}

interface ThreadCardProps {
  thread: Thread
  defaultExpanded?: boolean
}

/** 置信度 → 展示文案与配色（阈值与后端 app/threads/stats.py 一致） */
const CONFIDENCE_META: Record<string, { label: string; cls: string }> = {
  high: { label: '高', cls: 'bg-emerald-50 text-emerald-700' },
  medium: { label: '中', cls: 'bg-amber-50 text-amber-700' },
  low: { label: '低', cls: 'bg-gray-100 text-gray-500' },
}

/** Thread 生命周期徽章：更新中 / 观察中 / 历史事件 */
function ThreadStatusBadge({ lastSeenAt }: { lastSeenAt: string }) {
  const status = deriveThreadStatus(lastSeenAt)
  const meta = THREAD_STATUS_META[status]
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[11px] font-medium shrink-0',
        meta.cls,
      )}
      title={`最近更新：${formatDistanceToNow(lastSeenAt)}`}
    >
      <span className={clsx('inline-block h-1.5 w-1.5 rounded-full', meta.dotCls)} aria-hidden="true" />
      {meta.label}
    </span>
  )
}

/**
 * 「为什么聚为一个 Thread」画像条：
 * 用一句自然语言 + 三个指标 chip 解释聚合依据（AIHOT "为什么热" 的本地化）。
 */
function ThreadStatsBand({ stats }: { stats: ThreadStats }) {
  const pct = stats.similarity_avg != null ? Math.round(stats.similarity_avg * 100) : null
  const confidence = stats.confidence ? CONFIDENCE_META[stats.confidence] : null

  const caption = stats.item_count <= 1
    ? '目前只有 1 条报道，后续相似内容会自动聚合到这里。'
    : `${stats.item_count} 条报道来自 ${stats.platform_count} 个平台`
      + (pct != null ? `，与首发报道的平均匹配相似度 ${pct}%` : '')
      + (stats.recent_24h_count > 0 ? `，最近 24 小时仍在更新（+${stats.recent_24h_count} 条）` : '')
      + '。'

  return (
    <div className="border-t border-gray-100 bg-gray-50/60 px-4 py-3">
      <div className="flex items-center gap-1.5 text-xs font-medium text-gray-600 mb-1.5">
        <Flame className="h-3.5 w-3.5 text-orange-500" aria-hidden="true" />
        为什么聚为一个 Thread？
      </div>
      <p className="text-xs text-gray-500 leading-relaxed mb-2">{caption}</p>
      <div className="flex flex-wrap gap-2">
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-white ring-1 ring-gray-200 text-gray-600"
          title="覆盖的平台数量；跨平台共识越多，事件可信度越高"
        >
          <Globe className="h-3 w-3 text-gray-400" aria-hidden="true" />
          {stats.platform_count} 平台
        </span>
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-white ring-1 ring-gray-200 text-gray-600"
          title="最近 24 小时新聚合的报道数"
        >
          <TrendingUp className="h-3 w-3 text-gray-400" aria-hidden="true" />
          24h 新增 {stats.recent_24h_count}
        </span>
        {confidence && (
          <span
            className={clsx(
              'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs',
              confidence.cls,
            )}
            title={pct != null ? `同事件其他报道与首发报道的平均匹配相似度 ${pct}%` : '聚合匹配置信度'}
          >
            <Gauge className="h-3 w-3 opacity-70" aria-hidden="true" />
            聚类置信度 {confidence.label}
          </span>
        )}
      </div>
    </div>
  )
}

export function ThreadCard({ thread, defaultExpanded = false }: ThreadCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  // Fetch thread details (with items) only when expanded
  const { data: details, isError: detailsError, refetch: refetchDetails } = useQuery({
    queryKey: queryKeys.threads.detail(thread.id),
    queryFn: () => threadsApi.get(thread.id),
    enabled: expanded,
  })

  const spanDays = Math.floor(
    (new Date(thread.last_seen_at).getTime() - new Date(thread.first_seen_at).getTime()) / 86_400_000
  )
  // "5 天前 ~ 2 小时前"可读性差，改为"持续 N 天 + 最近更新时间"
  const timeSpanText = spanDays >= 1
    ? `持续 ${spanDays} 天，更新于 ${formatDistanceToNow(thread.last_seen_at)}`
    : formatDistanceToNow(thread.last_seen_at)

  const items = details?.items || []

  return (
    <div className="card overflow-hidden">
      {/* Thread header */}
      <button
        onClick={() => setExpanded(e => !e)}
        aria-expanded={expanded}
        className={clsx(
          'w-full flex items-center gap-3 px-4 py-3 text-left transition-colors',
          'hover:bg-gray-50',
          expanded && 'bg-gray-50/50'
        )}
      >
        {/* Expand/collapse chevron */}
        <span className="text-gray-400 shrink-0">
          {expanded
            ? <ChevronDown className="h-5 w-5" />
            : <ChevronRight className="h-5 w-5" />
          }
        </span>

        {/* Thread icon */}
        <div className="h-8 w-8 rounded-lg bg-primary-100 flex items-center justify-center shrink-0">
          <Rss className="h-4 w-4 text-primary-600" />
        </div>

        {/* Thread info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-gray-900 truncate">{thread.title}</span>
            <ThreadStatusBadge lastSeenAt={thread.last_seen_at} />
          </div>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            {/* Platform badges */}
            {(thread.platforms || []).slice(0, 5).map(p => (
              <PlatformBadge key={p} name={p} />
            ))}
            {(thread.platforms?.length || 0) > 5 && (
              <span className="text-xs text-gray-400">+{(thread.platforms?.length || 0) - 5}</span>
            )}
          </div>
        </div>

        {/* Stats */}
        <div className="text-right shrink-0">
          <div className="text-sm font-medium text-gray-900 flex items-center justify-end gap-1.5">
            {typeof thread.hotness === 'number' && thread.hotness >= 0.05 && (
              <span
                className="text-orange-500"
                title="热度：每个独立来源只计一次，随时间每 24 小时减半，48 小时无更新归零"
              >
                🔥 {thread.hotness.toFixed(1)}
              </span>
            )}
            <span>{thread.item_count} 条</span>
          </div>
          <div className="text-xs text-gray-400 mt-0.5">{timeSpanText}</div>
        </div>
      </button>

      {/* Items in thread */}
      {expanded && (
        detailsError ? (
          <div className="border-t border-gray-100 px-4 py-3 text-sm text-gray-500">
            加载失败
            <button
              type="button"
              onClick={() => refetchDetails()}
              className="ml-2 text-primary-600 hover:underline"
            >
              重试
            </button>
          </div>
        ) : items.length > 0 ? (
          <div className="border-t border-gray-100">
            {details?.stats && <ThreadStatsBand stats={details.stats} />}
            <div className="divide-y divide-gray-100">
              {items.map(item => (
                <div key={item.id} className="flex items-start gap-0">
                  <div className="w-1 self-stretch shrink-0 bg-primary-200" />
                  <div className="flex-1 min-w-0 pl-3 pr-4 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs text-gray-400">{item.task_name}</span>
                          {!item.is_read && (
                            <span className="inline-block h-1.5 w-1.5 rounded-full bg-primary-500" />
                          )}
                        </div>
                        <h3 className="text-sm font-medium text-gray-900 leading-snug">
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="hover:text-primary-600 transition-colors"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {item.title}
                            <ExternalLink className="h-3 w-3 inline ml-1 opacity-50" />
                          </a>
                        </h3>
                        <ClampText text={item.summary} className="text-xs text-gray-500 mt-1" />
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {item.is_starred && (
                          <Star className="h-4 w-4 text-yellow-400 fill-yellow-400" />
                        )}
                        <span className="text-xs text-gray-400">
                          {formatDistanceToNow(item.fetched_at)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="border-t border-gray-100 px-4 py-3 text-sm text-gray-500">
            {details ? '暂无内容' : '加载中...'}
          </div>
        )
      )}
    </div>
  )
}
