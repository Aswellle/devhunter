import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { ChevronDown, ChevronRight, Rss, Sparkles, TrendingUp } from 'lucide-react'
import { clsx } from 'clsx'
import { threadsApi } from '../api/threads'
import { userPrefsApi } from '../api/user_prefs'
import { queryKeys } from '../api/queryKeys'
import { formatDistanceToNow } from '../utils/time'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'
import type { RecommendedItem, ThreadWithItems } from '../types'

type Tab = 'recommended' | 'threads'

/** 按平台图标配色 */
const PLATFORM_COLORS: Record<string, string> = {
  '掘金':      'text-yellow-500',
  '少数派':    'text-orange-500',
  'V2EX':      'text-blue-400',
  '知乎':      'text-blue-500',
  'GitHub':    'text-gray-700',
  'Hacker News': 'text-orange-600',
  'Reddit':    'text-red-500',
  'Bilibili':  'text-pink-500',
  '小红书':    'text-red-400',
}

export function RecommendPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>((searchParams.get('tab') as Tab) || 'recommended')

  // Sync tab to URL
  useEffect(() => {
    const params = new URLSearchParams(searchParams)
    if (tab === 'recommended') params.delete('tab')
    else params.set('tab', tab)
    setSearchParams(params, { replace: true })
  }, [tab, setSearchParams])

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6">
      {/* Header */}
      <div className="mb-5">
        <h1 className="text-xl font-bold text-gray-900">今日推荐</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {tab === 'recommended'
            ? '基于你的兴趣偏好精选内容'
            : '多平台热点话题聚合'}
        </p>
      </div>

      <div role="tablist" aria-label="推荐内容筛选" className="flex items-center gap-1 p-1 bg-gray-100 rounded-lg w-fit mb-5">
        <TabButton
          active={tab === 'recommended'}
          onClick={() => setTab('recommended')}
          icon={<Sparkles className="h-4 w-4" />}
          label="为你推荐"
        />
        <TabButton
          active={tab === 'threads'}
          onClick={() => setTab('threads')}
          icon={<TrendingUp className="h-4 w-4" />}
          label="热点聚合"
        />
      </div>

      {/* Content */}
      {tab === 'recommended' ? <RecommendedTab /> : <ThreadsTab />}
    </div>
  )
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={clsx(
        'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all',
        active
          ? 'bg-white text-gray-900 shadow-sm'
          : 'text-gray-500 hover:text-gray-700',
      )}
    >
      {icon}
      {label}
    </button>
  )
}

// ── 为你推荐 Tab ─────────────────────────────────────────────
function RecommendedTab() {
  // F2: 使用规范化的 query key
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: queryKeys.recommendations.home(),
    queryFn: () => userPrefsApi.getRecommendations({ limit: 20, exclude_read: true }),
    staleTime: 30_000,
  })

  if (isLoading) {
    return <div className="flex justify-center py-16"><Spinner /></div>
  }

  if (isError) {
    return (
      <Empty
        title="加载失败"
        description="推荐内容加载出错，请检查网络连接后重试"
        action={
          <button onClick={() => refetch()} className="btn-primary">
            重试
          </button>
        }
      />
    )
  }

  if (!data?.items.length) {
    return (
      <Empty
        icon={Sparkles}
        title="暂无推荐内容"
        description="设置你的兴趣偏好，系统将为你精选相关内容"
      />
    )
  }

  return (
    <div className="space-y-2">
      {data.items.map((item: RecommendedItem) => (
        <RecommendedItemCard key={item.id} item={item} />
      ))}
    </div>
  )
}

function RecommendedItemCard({ item }: { item: RecommendedItem }) {
  const score = Math.round(item.recommendation_score * 100)
  const platform = item.task_name ?? '未知来源'

  return (
    <div className="card p-4 flex items-start gap-3 hover:shadow-md transition-shadow">
      {/* 得分 */}
      <div className={clsx(
        'shrink-0 w-12 h-12 rounded-xl flex flex-col items-center justify-center',
        score >= 80 ? 'bg-primary-50' : 'bg-gray-50',
      )}>
        <span className={clsx(
          'text-lg font-bold',
          score >= 80 ? 'text-primary-600' : 'text-gray-600',
        )}>
          {score}
        </span>
        <span className="text-[10px] text-gray-400">分</span>
      </div>

      {/* 内容 */}
      <div className="flex-1 min-w-0">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-sm font-medium text-gray-900 hover:text-primary-600 transition-colors leading-snug line-clamp-2"
          onClick={() => {
            userPrefsApi.recordInteraction({ item_id: item.id, interaction_type: 'click' })
          }}
        >
          {item.title}
        </a>
        {item.summary && (
          <p className="text-xs text-gray-500 mt-1 line-clamp-2">{item.summary}</p>
        )}
        <div className="flex items-center gap-2 mt-2">
          <span className={clsx('text-xs font-medium', PLATFORM_COLORS[platform] ?? 'text-gray-400')}>
            {platform}
          </span>
          <span className="text-xs text-gray-300">·</span>
          <span className="text-xs text-gray-400">
            {formatDistanceToNow(item.fetched_at)}
          </span>
          {score >= 80 && (
            <>
              <span className="text-xs text-gray-300">·</span>
              <span className="text-xs text-primary-500 font-medium">推荐</span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── 热点聚合 Tab ─────────────────────────────────────────────
function ThreadsTab() {
  // F2: 使用规范化的 query key
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: queryKeys.threads.list({ per_page: 20 }),
    queryFn: () => threadsApi.list({ per_page: 20 }),
    staleTime: 30_000,
  })

  if (isLoading) {
    return <div className="flex justify-center py-16"><Spinner /></div>
  }

  if (isError) {
    return (
      <Empty
        title="加载失败"
        description="热点聚合加载出错，请检查网络连接后重试"
        action={
          <button onClick={() => refetch()} className="btn-primary">
            重试
          </button>
        }
      />
    )
  }

  if (!data?.items.length) {
    return (
      <Empty
        icon={Rss}
        title="暂无热点聚合"
        description="多平台讨论同一事件的内容将自动聚合为热点话题"
      />
    )
  }

  return (
    <div className="space-y-3">
      {(data.items as ThreadWithItems[]).map((thread) => (
        <ThreadCard key={thread.id} thread={thread} />
      ))}
    </div>
  )
}

function ThreadCard({ thread }: { thread: ThreadWithItems }) {
  const [expanded, setExpanded] = useState(false)
  const platforms = thread.platforms ?? []

  // F2: 使用规范化的 query key
  const { data: details, isError } = useQuery({
    queryKey: queryKeys.threads.detail(thread.id),
    queryFn: () => threadsApi.get(thread.id),
    enabled: expanded,
  })

  const items = details?.items || []

  if (isError) {
    return (
      <div className="card overflow-hidden">
        <div className="px-4 py-3 text-sm text-danger" role="alert">
          加载失败，请重试
        </div>
      </div>
    )
  }

  return (
    <div className="card overflow-hidden">
      <button

        onClick={() => setExpanded(e => !e)}
        aria-expanded={expanded}
        aria-controls={`thread-items-${thread.id}`}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
      >
        <span className="text-gray-400">
          {expanded ? (
            <ChevronDown className="h-5 w-5" />
          ) : (
            <ChevronRight className="h-5 w-5" />
          )}
        </span>
        <Rss className="h-4 w-4 text-primary-500 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-900 truncate">{thread.title}</span>
            {thread.item_count > 1 && (
              <span className="badge badge-primary">{thread.item_count} 条</span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            {platforms.slice(0, 3).map((p) => (
              <span key={p} className={clsx('text-xs font-medium', PLATFORM_COLORS[p] ?? 'text-gray-400')}>
                {p}
              </span>
            ))}
            {platforms.length > 3 && (
              <span className="text-xs text-gray-400">+{platforms.length - 3}</span>
            )}
            <span className="text-xs text-gray-300">·</span>
            <span className="text-xs text-gray-400">
              {formatDistanceToNow(thread.last_seen_at)}
            </span>
          </div>
        </div>
      </button>

      {/* Expanded items */}
      {expanded && (
        <div id={`thread-items-${thread.id}`}>
          {items.length > 0 ? (
            <div className="border-t border-gray-100 divide-y divide-gray-100">
              {items.map((item) => (
                <div key={item.id} className="flex items-start gap-2 px-4 py-3">
                  <div className="flex-1 min-w-0">
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-gray-700 hover:text-primary-600 transition-colors line-clamp-2"
                      onClick={() => {
                        userPrefsApi.recordInteraction({ item_id: item.id, interaction_type: 'click' })
                      }}
                    >
                      {item.title}
                    </a>
                    {item.summary && (
                      <p className="text-xs text-gray-400 mt-0.5 line-clamp-1">{item.summary}</p>
                    )}
                    <div className="flex items-center gap-2 mt-1">
                      {item.task_name && (
                        <span className={clsx('text-xs', PLATFORM_COLORS[item.task_name] ?? 'text-gray-400')}>
                          {item.task_name}
                        </span>
                      )}
                      <span className="text-xs text-gray-400">
                        {formatDistanceToNow(item.fetched_at)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="border-t border-gray-100 px-4 py-3 text-sm text-gray-500">
              {details ? '暂无内容' : '加载中...'}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
