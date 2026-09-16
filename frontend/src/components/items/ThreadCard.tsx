import { useState } from 'react'
import { ChevronDown, ChevronRight, ExternalLink, Star, Rss } from 'lucide-react'
import { clsx } from 'clsx'
import { useQuery } from '@tanstack/react-query'
import type { Thread, ThreadWithItems } from '../../types'
import { formatDistanceToNow } from '../../utils/time'
import { threadsApi } from '../../api/threads'

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

export function ThreadCard({ thread, defaultExpanded = false }: ThreadCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  // Fetch thread details (with items) only when expanded
  const { data: details } = useQuery({
    queryKey: ['thread-detail', thread.id],
    queryFn: () => threadsApi.get(thread.id),
    enabled: expanded,
  })

  const timeSpan =
    new Date(thread.last_seen_at).getTime() - new Date(thread.first_seen_at).getTime()
  const timeSpanText = timeSpan > 0
    ? `${formatDistanceToNow(thread.first_seen_at)} ~ ${formatDistanceToNow(thread.last_seen_at)}`
    : formatDistanceToNow(thread.first_seen_at)

  const items = details?.items || []

  return (
    <div className="card overflow-hidden">
      {/* Thread header */}
      <button
        onClick={() => setExpanded(e => !e)}
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
          <div className="text-sm font-medium text-gray-900">{thread.item_count} 条</div>
          <div className="text-xs text-gray-400 mt-0.5">{timeSpanText}</div>
        </div>
      </button>

      {/* Items in thread */}
      {expanded && (
        items.length > 0 ? (
          <div className="border-t border-gray-100">
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
                        {item.summary && (
                          <p className="text-xs text-gray-500 mt-1 line-clamp-2">
                            {item.summary}
                          </p>
                        )}
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
