import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { Rss, Sparkles, TrendingUp, Layers, RefreshCw } from 'lucide-react'
import { clsx } from 'clsx'
import { toast } from 'react-hot-toast'
import { threadsApi } from '../api/threads'
import { userPrefsApi } from '../api/user_prefs'
import { queryKeys } from '../api/queryKeys'
import { errorMessage } from '../api/client'
import { formatDistanceToNow } from '../utils/time'
import { isSafeExternalUrl } from '../utils/url'
import { ThreadCard } from '../components/items/ThreadCard'
import { ReasonBadges } from '../components/recommend/ReasonBadges'
import { ClampText } from '../components/ui/ClampText'
import { Pagination } from '../components/ui/Pagination'
import { PullToRefresh } from '../components/ui/PullToRefresh'
import { ScorePill } from '../components/ui/ScorePill'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'
import type { RecommendedItem } from '../types'
import { usePageTitle } from '../hooks/usePageTitle'

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
  usePageTitle('推荐')
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
      <ClampText text={item.summary} readMoreHref={item.url} className="text-xs text-gray-500 mt-1" />
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
function StatChip({ label, tone = 'muted' }: { label: string; tone?: 'muted' | 'success' | 'warn' }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs ring-1',
        tone === 'success' && 'bg-emerald-50 text-emerald-700 ring-emerald-200',
        tone === 'warn' && 'bg-amber-50 text-amber-700 ring-amber-200',
        tone === 'muted' && 'bg-white text-gray-600 ring-gray-200',
      )}
    >
      {label}
    </span>
  )
}

function ThreadsTab() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [multiOnly, setMultiOnly] = useState(false)
  const [windowHours, setWindowHours] = useState(72)

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: queryKeys.threads.list({
      page,
      per_page: 20,
      min_items: multiOnly ? 2 : 1,
    }),
    queryFn: () =>
      threadsApi.list({
        page,
        per_page: 20,
        min_items: multiOnly ? 2 : 1,
      }),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })

  // 聚合概览：解释"为什么现在只有单条报道"以及还剩多少待补聚
  const { data: overview } = useQuery({
    queryKey: queryKeys.threads.overview(windowHours),
    queryFn: () => threadsApi.overview(windowHours),
    staleTime: 30_000,
  })

  const consolidateMutation = useMutation({
    mutationFn: () => threadsApi.consolidate(windowHours),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: queryKeys.threads.all })
      qc.invalidateQueries({ queryKey: queryKeys.items.all })
      const swept = result.orphans_clustered + result.orphans_swept
      if (result.merged_threads > 0 || swept > 0) {
        toast.success(
          `聚合完成：合并 ${result.merged_threads} 个单条热点、补聚 ${swept} 条内容，` +
            `当前 ${result.threads_multi} 个多来源热点`,
        )
      } else {
        toast(
          '本轮没有可归并的报道：热点需要至少两个来源讨论同一事件；也可以在采集结果中勾选多条手动聚合。',
          { duration: 6000 },
        )
      }
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '聚合失败，请稍后重试')),
  })
  const busy = consolidateMutation.isPending

  return (
    <div className="space-y-4">
      {/* 聚合概览与执行入口 */}
      <div className="card p-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-gray-900 flex items-center gap-1.5">
              <Layers className="h-4 w-4 text-primary-500" aria-hidden="true" />
              聚合概览
            </h2>
            <p className="text-xs text-gray-500 mt-1 leading-relaxed">
              每次采集后自动聚类；另有每小时一次的增量合并，把仍单独成条的报道与相近热点归并。
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <label className="text-xs text-gray-500 inline-flex items-center gap-1">
              窗口
              <select
                value={windowHours}
                onChange={(e) => {
                  setWindowHours(Number(e.target.value))
                  setPage(1)
                }}
                className="rounded border border-gray-200 bg-white px-1.5 py-1 text-xs text-gray-600 focus:border-primary-500 focus:outline-none"
                aria-label="聚合候选窗口"
              >
                <option value={24}>24 小时</option>
                <option value={72}>72 小时</option>
                <option value={168}>7 天</option>
              </select>
            </label>
            <button
              type="button"
              onClick={() => consolidateMutation.mutate()}
              disabled={busy}
              className="btn-primary btn-sm"
            >
              <RefreshCw
                className={clsx('h-3.5 w-3.5', busy && 'animate-spin')}
                aria-hidden="true"
              />
              {busy ? '聚合中…' : '立即聚合'}
            </button>
          </div>
        </div>

        {overview && (
          <>
            <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
              <StatChip
                label={`近 ${windowHours}h ${overview.active_discussion_sources} 个讨论来源`}
              />
              <StatChip label={`${overview.discussion_items_in_window} 条内容`} />
              <StatChip
                label={`多来源热点 ${overview.threads_multi}`}
                tone="success"
              />
              <StatChip
                label={`单条待聚合 ${overview.threads_single}`}
                tone={overview.threads_single > 0 ? 'warn' : 'muted'}
              />
              {overview.orphan_items > 0 && (
                <StatChip label={`待补聚 ${overview.orphan_items}`} tone="warn" />
              )}
              {overview.last_consolidation && (
                <span className="text-gray-400">
                  上次聚合：{formatDistanceToNow(overview.last_consolidation.at)}
                  （{overview.last_consolidation.trigger === 'scheduled' ? '自动' : '手动'}）
                </span>
              )}
              {overview.recompute.running && (
                <span className="text-primary-600">全量重建进行中…</span>
              )}
            </div>

            {overview.active_discussion_sources < 2 && (
              <p className="mt-2.5 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800 leading-relaxed">
                近 {windowHours} 小时只有 {overview.active_discussion_sources} 个讨论型来源在产出内容。
                热点需要至少两个来源讨论同一事件；可到
                <Link to="/tasks" className="mx-0.5 font-medium underline">
                  任务管理
                </Link>
                添加讨论型来源（HN、V2EX、少数派等），或等待现有来源后续产出。
              </p>
            )}
            <p className="mt-2 text-xs text-gray-400 leading-relaxed">
              自动聚类认不出跨语种/表述差异的报道时，可到
              <Link to="/" className="mx-0.5 text-primary-600 hover:underline">
                采集结果
              </Link>
              勾选两条以上 →「聚合为热点」手动建立热点。
            </p>
          </>
        )}
      </div>

      <div className="flex items-center justify-between gap-2">
        <label className="inline-flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            checked={multiOnly}
            onChange={(e) => {
              setMultiOnly(e.target.checked)
              setPage(1)
            }}
            className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
          />
          只看多来源热点（≥2 条报道）
        </label>
        <span className="text-xs text-gray-400">
          {data ? `共 ${data.total} 个` : isFetching ? '加载中…' : ''}
        </span>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : isError ? (
        <Empty
          title="加载失败"
          description="热点聚合加载出错，请检查网络连接后重试"
          action={
            <button onClick={() => refetch()} className="btn-primary">
              重试
            </button>
          }
        />
      ) : !data?.items.length ? (
        multiOnly ? (
          <Empty
            icon={Layers}
            title="还没有多来源热点"
            description="自动聚类与每小时增量合并仍在运行；也可以先查看全部热点，或去采集结果手动聚合。"
            action={
              <button onClick={() => setMultiOnly(false)} className="btn-ghost">
                查看全部热点
              </button>
            }
          />
        ) : (
          <Empty
            icon={Rss}
            title="暂无热点聚合"
            description="多个来源讨论同一事件的内容会自动聚合为热点。先添加讨论型数据源并完成一次采集，或点击上方「立即聚合」补聚现有内容。"
            action={
              <div className="flex items-center gap-2">
                <Link to="/tasks" className="btn-primary">添加数据源</Link>
                <button
                  type="button"
                  onClick={() => consolidateMutation.mutate()}
                  disabled={busy}
                  className="btn-ghost"
                >
                  立即聚合
                </button>
              </div>
            }
          />
        )
      ) : (
        <div className={isFetching ? 'opacity-70 transition-opacity' : 'transition-opacity'}>
          <div className="space-y-3">
            {data.items.map((thread) => (
              <ThreadCard key={thread.id} thread={thread} defaultExpanded={false} />
            ))}
          </div>
          <Pagination
            page={page}
            total={data.total}
            perPage={data.per_page}
            onChange={setPage}
          />
        </div>
      )}
    </div>
  )
}

