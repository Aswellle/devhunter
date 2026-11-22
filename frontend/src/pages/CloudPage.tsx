/**
 * CloudPage.tsx
 * Floating word cloud display of scraped items.
 *
 * Design approach - Masonry cloud layout:
 * - JS balanced columns (vertical page scroll, no sideways column overflow)
 * - Each element floats gently with randomized CSS keyframe animations
 * - Solid pastel cards (no backdrop blur: 500+ blur layers tank scroll FPS)
 * - Same-title items cluster into one card: cluster count drives font size (+ ×N badge)
 * - Progressive infinite pagination: first paint waits for page 1 only,
 *   sentinel-driven load-more up to 1000 items with cross-page id dedup
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { Cloud } from 'lucide-react'
import { itemsApi } from '../api/items'
import { queryKeys } from '../api/queryKeys'
import { formatDateTime } from '../utils/time'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'
import type { Item } from '../types'
import { usePageTitle } from '../hooks/usePageTitle'

/**
 * 字号阶梯：以标题长度定基档，热度（同题聚簇大小）向上加档封顶。
 * 长标题即使在热簇里也只升到可读上限，避免撑爆卡片。
 */
const SIZE_LADDER = ['text-xs', 'text-sm', 'text-base', 'text-lg', 'text-xl'] as const

function getTitleSize(title: string, clusterSize: number): string {
  const len = title.length
  let tier = len <= 20 ? 3 : len <= 35 ? 2 : len <= 55 ? 1 : 0
  if (clusterSize >= 5) tier = Math.min(tier + 2, SIZE_LADDER.length - 1)
  else if (clusterSize >= 2) tier = Math.min(tier + 1, SIZE_LADDER.length - 1)
  return SIZE_LADDER[tier]
}

/** Pastel palette with glassmorphism for cloud aesthetic */
const CLOUD_PALETTES = [
  { bg: 'bg-sky-50/80', border: 'border-sky-200/60', text: 'text-sky-900', hover: 'hover:bg-sky-100/90' },
  { bg: 'bg-rose-50/80', border: 'border-rose-200/60', text: 'text-rose-900', hover: 'hover:bg-rose-100/90' },
  { bg: 'bg-emerald-50/80', border: 'border-emerald-200/60', text: 'text-emerald-900', hover: 'hover:bg-emerald-100/90' },
  { bg: 'bg-amber-50/80', border: 'border-amber-200/60', text: 'text-amber-900', hover: 'hover:bg-amber-100/90' },
  { bg: 'bg-violet-50/80', border: 'border-violet-200/60', text: 'text-violet-900', hover: 'hover:bg-violet-100/90' },
  { bg: 'bg-teal-50/80', border: 'border-teal-200/60', text: 'text-teal-900', hover: 'hover:bg-teal-100/90' },
  { bg: 'bg-fuchsia-50/80', border: 'border-fuchsia-200/60', text: 'text-fuchsia-900', hover: 'hover:bg-fuchsia-100/90' },
  { bg: 'bg-cyan-50/80', border: 'border-cyan-200/60', text: 'text-cyan-900', hover: 'hover:bg-cyan-100/90' },
]

/** Floating animation keyframes - varied movement patterns */
const FLOAT_ANIMATIONS = `
  @media (prefers-reduced-motion: no-preference) {
    @keyframes float-drift-1 {
      0%, 100% { transform: translateY(0px) rotate(0deg); }
      33% { transform: translateY(-12px) rotate(0.8deg); }
      66% { transform: translateY(-6px) rotate(-0.5deg); }
    }
    @keyframes float-drift-2 {
      0%, 100% { transform: translateY(0px) rotate(0deg); }
      25% { transform: translateY(-8px) rotate(-0.6deg); }
      75% { transform: translateY(-14px) rotate(0.4deg); }
    }
    @keyframes float-drift-3 {
      0%, 100% { transform: translateY(0px) rotate(0deg); }
      40% { transform: translateY(-16px) rotate(1deg); }
      70% { transform: translateY(-5px) rotate(-0.3deg); }
    }
    @keyframes float-drift-4 {
      0%, 100% { transform: translateY(0px) rotate(0deg); }
      30% { transform: translateY(-10px) rotate(-0.7deg); }
      60% { transform: translateY(-18px) rotate(0.6deg); }
    }
    @keyframes float-drift-5 {
      0%, 100% { transform: translateY(0px) rotate(0deg); }
      50% { transform: translateY(-20px) rotate(0.5deg); }
    }
    @keyframes shimmer {
      0%, 100% { opacity: 0.7; }
      50% { opacity: 1; }
    }
  }
`

/** Animation names for variety */
const FLOAT_FNS = ['float-drift-1', 'float-drift-2', 'float-drift-3', 'float-drift-4', 'float-drift-5']

/**
 * 断点与 Tailwind sm/lg/xl 对齐的均衡列数。
 * 固定高度容器里的 CSS 多列会横向溢出（新列向右生成），
 * 这里改用 JS 均衡列瀑布流，让 <main> 天然纵向滚动。
 */
const COLUMN_BREAKPOINTS = [
  { query: '(min-width: 1280px)', columns: 4 },
  { query: '(min-width: 1024px)', columns: 3 },
  { query: '(min-width: 640px)', columns: 2 },
] as const

function resolveColumnCount(): number {
  for (const bp of COLUMN_BREAKPOINTS) {
    if (window.matchMedia(bp.query).matches) return bp.columns
  }
  return 1
}

function useColumnCount(): number {
  const [columns, setColumns] = useState(resolveColumnCount)
  useEffect(() => {
    const mqls = COLUMN_BREAKPOINTS.map((bp) => window.matchMedia(bp.query))
    const update = () => setColumns(resolveColumnCount())
    mqls.forEach((mql) => mql.addEventListener('change', update))
    return () => mqls.forEach((mql) => mql.removeEventListener('change', update))
  }, [])
  return columns
}

/** Chinese domain → friendly Chinese name map */
const SITE_NAME_MAP: Record<string, string> = {
  'juejin.cn':      '掘金',
  'sspai.com':      '少数派',
  'v2ex.com':       'V2EX',
  'zhihu.com':      '知乎',
  'xiaohongshu.com': '小红书',
  'jianshu.com':    '简书',
  'weibo.com':      '微博',
  'bilibili.com':   '哔哩哔哩',
  'b23.tv':        '哔哩哔哩',
  'weixin.qq.com':  '微信',
  'baidu.com':      '百度',
  'csdn.net':       'CSDN',
  'imooc.com':      '慕课',
  'nowcoder.com':   '牛客',
  'juejin.net':     '掘金',
  'github.com':     'GitHub',
  'dev.to':         'Dev.to',
  'reddit.com':     'Reddit',
  'hacker.news':    'Hacker News',
  'indiehackers.com': 'Indie Hackers',
}

/** 站点名解析结果按 host 缓存，避免 500+ 卡片每次渲染重复解析 */
const SITE_NAME_CACHE = new Map<string, string>()

/** Extract clean site name from URL (longest known domain suffix wins, Chinese name preferred) */
function getSiteName(url: string): string {
  let host: string
  try {
    host = new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return '未知站点'
  }
  const cached = SITE_NAME_CACHE.get(host)
  if (cached) return cached

  let name = SITE_NAME_MAP[host]
  if (!name) {
    const parts = host.split('.')
    // 后缀匹配：让 blog.zhihu.com、m.sspai.com 命中主域的友好名
    for (let i = 1; i < parts.length - 1; i++) {
      const mapped = SITE_NAME_MAP[parts.slice(i).join('.')]
      if (mapped) {
        name = mapped
        break
      }
    }
    if (!name) {
      // Fallback: capitalize first letter of main domain
      if (parts[0]) parts[0] = parts[0].charAt(0).toUpperCase() + parts[0].slice(1)
      name = parts.join('.')
    }
  }
  SITE_NAME_CACHE.set(host, name)
  return name
}

/**
 * 渐进分页：首屏只等第 1 页，触底自动续页。
 * 上限 1000：无模糊卡 + content-visibility 跳渲染下可承受的量级，
 * 同时防止结果云无限膨胀拖垮内存。
 */
const PER_PAGE = 100
const MAX_ITEMS = 1000

interface CloudPageResult {
  items: Item[]
  total: number
}

async function fetchCloudPage({ pageParam }: { pageParam: number }): Promise<CloudPageResult> {
  const response = await itemsApi.list({ page: pageParam, per_page: PER_PAGE })
  return { items: response.items, total: response.total }
}


export function CloudPage() {
  usePageTitle('结果云')
  const query = useInfiniteQuery({
    queryKey: queryKeys.items.cloud(),
    queryFn: fetchCloudPage,
    initialPageParam: 1,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((sum, page) => sum + page.items.length, 0)
      if (!lastPage.items.length) return undefined
      if (loaded >= MAX_ITEMS) return undefined
      if (loaded >= lastPage.total) return undefined
      return allPages.length + 1
    },
    staleTime: 30_000, // 30s cache
  })
  const { isLoading, isError, refetch, hasNextPage, isFetchingNextPage, fetchNextPage } = query

  /**
   * 跨页按 id 去重：created_at DESC 分页在滚动窗口期间有新条目插入时，
   * 页与页之间会出现窗口漂移，同一条目可能落在相邻两页里。
   */
  const { items, cloudTotal, cloudTruncated } = useMemo(() => {
    const seen = new Set<string>()
    const deduped: Item[] = []
    const pages = query.data?.pages ?? []
    for (const page of pages) {
      for (const item of page.items) {
        if (deduped.length >= MAX_ITEMS) break
        // 脏数据不过云：无标题渲染空卡，无链接的卡片可交互性为零
        if (!item.title?.trim() || !item.url) continue
        if (seen.has(item.id)) continue
        seen.add(item.id)
        deduped.push(item)
      }
    }
    const total = pages.length ? pages[pages.length - 1].total : 0
    return { items: deduped, cloudTotal: total, cloudTruncated: total > deduped.length }
  }, [query.data])

  /** 触底自动续页：提前 600px 预取，衔接滑动节奏 */
  const sentinelRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) fetchNextPage()
      },
      { rootMargin: '600px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  /**
   * 词云语义：同题归簇。重爬产生的同题条目只渲染一条代表卡，
   * 聚簇大小作为热度权重驱动字号，并以 ×N 徽标示众。
   */
  const displayEntries = useMemo(() => {
    const normTitle = (t: string) => t.trim().toLowerCase().replace(/\s+/g, '')
    const counts = new Map<string, number>()
    for (const item of items) {
      const key = normTitle(item.title)
      counts.set(key, (counts.get(key) ?? 0) + 1)
    }
    const seen = new Set<string>()
    const entries: { item: Item; clusterSize: number }[] = []
    for (const item of items) {
      const key = normTitle(item.title)
      if (seen.has(key)) continue
      seen.add(key)
      entries.push({ item, clusterSize: counts.get(key) ?? 1 })
    }
    return entries
  }, [items])

  /** 全局 index 保持稳定，色板/动画不随列数变化跳变 */
  const columnCount = useColumnCount()
  const columnEntries = useMemo(() => {
    const buckets: { item: Item; clusterSize: number; index: number }[][] = Array.from(
      { length: columnCount },
      () => [],
    )
    displayEntries.forEach((entry, index) => buckets[index % columnCount].push({ ...entry, index }))
    return buckets
  }, [displayEntries, columnCount])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner />
      </div>
    )
  }

  if (isError && !items.length) {
    return (
      <div className="flex items-center justify-center h-full">
        <Empty
          icon={Cloud}
          title="数据加载失败"
          description="采集结果加载出错，请检查网络连接后重试"
          action={
            <button onClick={() => refetch()} className="btn-primary">
              重试
            </button>
          }
        />
      </div>
    )
  }

  if (!items?.length) {
    return (
      <div className="flex items-center justify-center h-full">
        <Empty
          icon={Cloud}
          title="暂无采集结果"
          description="当有采集任务完成后，这里将展示飘浮的词云"
        />
      </div>
    )
  }

  return (
    <div className="relative w-full overflow-hidden bg-sky-50/50">
      {/* Inject floating animation keyframes */}
      <style>{FLOAT_ANIMATIONS}</style>

      {/* Subtle ambient background */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute -top-20 -left-20 w-96 h-96 bg-sky-100/50 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-72 h-72 bg-sky-100/40 rounded-full blur-3xl" />
      </div>

      {/* Masonry cloud layout：均衡列瀑布流，交给 <main> 纵向滚动 */}
      <div className="relative p-6 flex items-start gap-4">
        {columnEntries.map((column, columnIndex) => (
          <div key={columnIndex} className="flex-1 min-w-0 flex flex-col">
            {column.map(({ item, clusterSize, index }) => {
              const palette = CLOUD_PALETTES[index % CLOUD_PALETTES.length]
              const animName = FLOAT_FNS[index % FLOAT_FNS.length]
              const animDuration = `${18 + (index % 12)}s`
              const animDelay = `${-(index * 1.3)}s`
              // 爬取内容的外链只放行 http(s)（纵深防御，后端已有校验）
              const safeHref = /^https?:\/\//i.test(item.url) ? item.url : undefined

              return (
                <div
                  key={item.id}
                  className={`
                    mb-4 rounded-2xl px-4 py-3
                    border shadow-sm
                    transition-colors duration-300 ease-out
                    ${palette.bg} ${palette.border} ${palette.text} ${palette.hover}
                  `}
                  style={{
                    animation: `${animName} ${animDuration} ease-in-out infinite`,
                    animationDelay: animDelay,
                    transformOrigin: 'center top',
                    contentVisibility: 'auto',
                    containIntrinsicSize: '0 120px',
                  } as React.CSSProperties}
                >

                  <a
                    href={safeHref}
                    target={safeHref ? '_blank' : undefined}
                    rel="noopener noreferrer"
                    className={`font-medium ${getTitleSize(item.title, clusterSize)} leading-relaxed hover:underline block`}
                    style={{ wordBreak: 'break-word' }}
                  >
                    {item.title}
                  </a>

                  {item.summary?.trim() && (
                    <p className="mt-1.5 text-xs leading-relaxed opacity-70 line-clamp-2">
                      {item.summary}
                    </p>
                  )}

                  {/* Metadata row */}
                  <div className="flex items-center gap-2 mt-2 text-xs opacity-60">
                    <span className="font-medium truncate max-w-[140px]">{getSiteName(item.url)}</span>
                    {clusterSize > 1 && (
                      <span
                        className="rounded-full bg-white/60 px-1.5 py-0.5 font-medium"
                        title={`共 ${clusterSize} 条相同标题`}
                      >
                        ×{clusterSize}
                      </span>
                    )}
                    <span className="opacity-40">|</span>
                    <time dateTime={item.fetched_at} className="whitespace-nowrap">
                      {formatDateTime(item.fetched_at)}
                    </time>
                  </div>
                </div>
              )
            })}
          </div>
        ))}
      </div>

      {/* 触底续页哨兵：失败时保留已加载内容，点击重试 */}
      <div ref={sentinelRef} className="relative py-6 flex justify-center">
        {isFetchingNextPage && <Spinner />}
        {!isFetchingNextPage && isError && items.length > 0 && (
          <button onClick={() => fetchNextPage()} className="btn-primary">
            加载更多失败，重试
          </button>
        )}
      </div>

      {/* Stats overlay：跟随视口右下角，移动端让开底部导航 */}
      <div className="fixed bottom-20 md:bottom-4 right-4 z-10 text-xs text-gray-700 bg-white/80 px-3 py-1.5 rounded-full shadow-sm">
        {cloudTruncated
          ? `共 ${cloudTotal} 条采集结果 · 已加载 ${items.length} 条`
          : cloudTotal > displayEntries.length
            ? `共 ${cloudTotal} 条采集结果 · 聚合为 ${displayEntries.length} 组`
            : `共 ${cloudTotal} 条采集结果`}
      </div>
    </div>
  )
}
