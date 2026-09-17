/**
 * CloudPage.tsx
 * Floating word cloud display of scraped items.
 *
 * Design approach - Masonry cloud layout:
 * - CSS columns create natural flow without grid alignment
 * - Each element floats gently with randomized CSS keyframe animations
 * - Titles determine their own size (no truncation)
 * - Glassmorphism cards with soft pastel palette
 * - Handles pagination to fetch all available items (up to 500)
 */
import { useQuery } from '@tanstack/react-query'
import { Cloud } from 'lucide-react'
import { itemsApi } from '../api/items'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'

/** Font size based on title character count - fluid scaling */
function getTitleSize(title: string): string {
  const len = title.length
  if (len <= 20) return 'text-lg'
  if (len <= 35) return 'text-base'
  if (len <= 55) return 'text-sm'
  return 'text-xs'
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

/** Extract clean site name from URL (domain only, Chinese name preferred) */
function getSiteName(url: string): string {
  try {
    const u = new URL(url)
    let host = u.hostname.replace(/^www\./, '')
    if (SITE_NAME_MAP[host]) return SITE_NAME_MAP[host]
    // Fallback: capitalize first letter of main domain
    const parts = host.split('.')
    if (parts[0]) parts[0] = parts[0].charAt(0).toUpperCase() + parts[0].slice(1)
    return parts.join('.')
  } catch {
    return '未知站点'
  }
}

/**
 * Fetch all items across multiple pages (backend caps at 100 per page)
 */
async function fetchAllCloudItems(): Promise<any[]> {
  const MAX_TOTAL = 500 // Cap at 500 for performance
  const PER_PAGE = 100
  let allItems: any[] = []
  let page = 1

  while (allItems.length < MAX_TOTAL) {
    try {
      const response = await itemsApi.list({ page, per_page: PER_PAGE })
      if (!response.items.length) break
      allItems = [...allItems, ...response.items]
      // PaginatedResponse has total/page/per_page but no has_more; use total to decide stop
      if (allItems.length >= response.total) break
      page++
    } catch (err) {
      // 部分数据降级：如果已有数据则返回已获取部分，否则抛出
      if (allItems.length > 0) {
        console.warn(`[CloudPage] 分页获取在第 ${page} 页中断，返回已获取的 ${allItems.length} 条数据`, err)
        break
      }
      throw err
    }
  }

  return allItems.slice(0, MAX_TOTAL)
}


export function CloudPage() {
  const { data: items, isLoading, isError } = useQuery({
    queryKey: ['cloud-items'],
    queryFn: fetchAllCloudItems,
    staleTime: 30_000, // 30s cache
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex items-center justify-center h-full">
        <Empty
          icon={Cloud}
          title="数据加载失败"
          description="采集结果加载出错，请检查网络连接后重试"
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
    <div className="relative w-full h-full overflow-hidden bg-sky-50/50">
      {/* Inject floating animation keyframes */}
      <style>{FLOAT_ANIMATIONS}</style>

      {/* Subtle ambient background */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute -top-20 -left-20 w-96 h-96 bg-sky-100/50 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-72 h-72 bg-sky-100/40 rounded-full blur-3xl" />
      </div>

      {/* Masonry cloud layout using CSS columns */}
      <div
        className="absolute inset-0 overflow-auto p-6 columns-1 sm:columns-2 lg:columns-3 xl:columns-4"
        style={{ columnGap: '16px' }}
      >
        {items.map((item, index) => {
          const palette = CLOUD_PALETTES[index % CLOUD_PALETTES.length]
          const animName = FLOAT_FNS[index % FLOAT_FNS.length]
          const animDuration = `${18 + (index % 12)}s`
          const animDelay = `${-(index * 1.3)}s`
          const depthZ = 10 + (index % 15)

          return (
            <div
              key={item.id}
              className={`
                break-inside-avoid mb-4 rounded-2xl px-4 py-3
                border backdrop-blur-md shadow-sm
                transition-all duration-300 ease-out
                ${palette.bg} ${palette.border} ${palette.text} ${palette.hover}
              `}
              style={{
                animation: `${animName} ${animDuration} ease-in-out infinite`,
                animationDelay: animDelay,
                zIndex: depthZ,
                transformOrigin: 'center top',
                contentVisibility: 'auto',
                containIntrinsicSize: '0 200px',
              } as React.CSSProperties}
            >

              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className={`font-medium ${getTitleSize(item.title)} leading-relaxed hover:underline block`}
                style={{ wordBreak: 'break-word' }}
              >
                {item.title}
              </a>

              {/* Metadata row */}
              <div className="flex items-center gap-2 mt-2 text-xs opacity-60">
                <span className="font-medium truncate max-w-[140px]">{getSiteName(item.url)}</span>
                <span className="opacity-40">|</span>
                <time dateTime={item.fetched_at} className="whitespace-nowrap">
                  {new Date(item.fetched_at).toLocaleString('zh-CN', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </time>
              </div>
            </div>
          )
        })}
      </div>

      {/* Stats overlay */}
      <div className="absolute bottom-4 right-4 text-xs text-gray-500/70 bg-white/50 px-3 py-1.5 rounded-full backdrop-blur-sm shadow-sm">
        共 {items.length} 条采集结果
      </div>
    </div>
  )
}
