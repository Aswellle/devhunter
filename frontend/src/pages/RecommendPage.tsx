import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Rss, Sparkles, TrendingUp } from 'lucide-react'
import { clsx } from 'clsx'
import { threadsApi } from '../api/threads'
import { userPrefsApi } from '../api/user_prefs'
import { queryKeys } from '../api/queryKeys'
import { formatDistanceToNow } from '../utils/time'
import { isSafeExternalUrl } from '../utils/url'
import { ThreadCard } from '../components/items/ThreadCard'
import { ReasonBadges } from '../components/recommend/ReasonBadges'
import { ClampText } from '../components/ui/ClampText'
import { PullToRefresh } from '../components/ui/PullToRefresh'
import { ScorePill } from '../components/ui/ScorePill'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'
import type { RecommendedItem } from '../types'

type Tab = 'recommended' | 'threads'

const TABS: { value: Tab; label: string }[] = [
  { value: 'recommended', label: '为你推荐' },
  { value: 'threads', label: '热点聚合' },
]

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
  const qc = useQueryClient()
  // 移动端下拉刷新：失效两个 tab 的查询，激活中的 tab 会自动重取
  const handlePullRefresh = () => Promise.allSettled([
    qc.invalidateQueries({ queryKey: queryKeys.recommendations.all }),
    qc.invalidateQueries({ queryKey: queryKeys.threads.all }),
  ])

  // Sync tab to URL
  useEffect(() => {
    const params = new URLSearchParams(searchParams)
    if (tab === 'recommended') params.delete('tab')
    else params.set('tab', tab)
    setSearchParams(params, { replace: true })
  }, [tab, searchParams, setSearchParams])

  // tablist 方向键导航（两个 tab：←/→ 均切换到另一个）
  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    e.preventDefault()
    const nextTab: Tab = tab === 'recommended' ? 'threads' : 'recommended'
    setTab(nextTab)
    const tabButtons = e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')
    tabButtons[TABS.findIndex((t) => t.value === nextTab)]?.focus()
  }

  return (
    <PullToRefresh onRefresh={handlePullRefresh}>
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

      <div
        role="tablist"
        aria-label="推荐内容筛选"
        onKeyDown={handleTabKeyDown}
        className="flex items-center gap-1 p-1 bg-gray-100 rounded-lg w-fit mb-5"
      >
        {TABS.map(({ value, label }) => (
          <TabButton
            key={value}
            active={tab === value}
            tabIndex={tab === value ? 0 : -1}
            onClick={() => setTab(value)}
            icon={value === 'recommended' ? <Sparkles className="h-4 w-4" /> : <TrendingUp className="h-4 w-4" />}
            label={label}
          />
        ))}
      </div>

      {/* Content */}
      {tab === 'recommended' ? <RecommendedTab /> : <ThreadsTab />}
    </div>
    </PullToRefresh>
  )
}

function TabButton({
  active,
  onClick,
  icon,
  label,
  tabIndex = 0,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
  tabIndex?: number
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      tabIndex={tabIndex}
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
    placeholderData: (prev) => prev,
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
    <div className="card p-4 hover:shadow-md transition-shadow">
      <a
        href={isSafeExternalUrl(item.url) ? item.url : undefined}
        target={isSafeExternalUrl(item.url) ? '_blank' : undefined}
        rel="noopener noreferrer"
        className="block text-sm font-medium text-gray-900 hover:text-primary-600 transition-colors leading-snug line-clamp-2"
        onClick={() => {
          userPrefsApi
            .recordInteraction({ item_id: item.id, interaction_type: 'click' })
            .catch(() => {})
        }}
      >
        {item.title}
      </a>
      <ReasonBadges reasons={item.recommendation_reasons} max={3} />
      <ClampText text={item.summary} className="text-xs text-gray-500 mt-1" />
      <div className="flex items-center gap-2 mt-2 flex-wrap">
        {/* 分级胶囊：≥80 主题色即"推荐"态，不再重复文字徽标 */}
        <ScorePill score={score} />
        <span className={clsx('text-xs font-medium', PLATFORM_COLORS[platform] ?? 'text-gray-400')}>
          {platform}
        </span>
        <span className="text-xs text-gray-300">·</span>
        <span className="text-xs text-gray-400">
          {formatDistanceToNow(item.fetched_at)}
        </span>
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
    placeholderData: (prev) => prev,
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
      {data.items.map((thread) => (
        <ThreadCard key={thread.id} thread={thread} defaultExpanded={false} />
      ))}
    </div>
  )
}

