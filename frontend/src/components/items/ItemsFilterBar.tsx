import { useEffect, useRef, useState } from 'react'
import { Search, X, Eye, EyeOff } from 'lucide-react'
import { FilterBar, type CategoryOption, type ReadStatusOption } from './FilterBar'
import type { Task } from '../../types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface FiltersState {
  search: string
  task_id: string
  starred: boolean | undefined
  is_read: boolean | undefined
}

interface ItemsFilterBarProps {
  filters: FiltersState
  onChange: (f: Partial<FiltersState>) => void
  tasks: Task[]
  /** Optional category counts grouped by task_id */
  categoryCounts?: Record<string, { total: number; unread: number }>
  /** Total item count (from API response) for the "全部" pill badge */
  totalCount?: number
}

// ── Helper: Convert tasks to category options ─────────────────────────────────

function tasksToCategories(
  tasks: Task[],
  categoryCounts?: Record<string, { total: number; unread: number }>
): CategoryOption[] {
  return tasks.map((task) => ({
    id: task.id,
    label: task.name,
    count: categoryCounts?.[task.id]?.total,
    unreadCount: categoryCounts?.[task.id]?.unread,
  }))
}

// ── Default read status options ───────────────────────────────────────────────

const DEFAULT_READ_STATUSES: ReadStatusOption[] = [
  { value: undefined, label: '全部', icon: null },
  { value: false, label: '未读', icon: <EyeOff className="h-3.5 w-3.5" /> },
  { value: true, label: '已读', icon: <Eye className="h-3.5 w-3.5" /> },
]

/** 搜索防抖：停输入 300ms 后才提交，避免逐键发起 API 请求 */
const SEARCH_DEBOUNCE_MS = 300

// ── ItemsFilterBar：搜索 + 任务/已读状态 FilterBar + 收藏开关 ─────────────────

export function ItemsFilterBar({ filters, onChange, tasks, categoryCounts, totalCount }: ItemsFilterBarProps) {
  const categories = tasksToCategories(tasks, categoryCounts)

  // 搜索输入使用本地 state，防抖后提交到 filters（驱动 URL 同步与查询）
  const [searchText, setSearchText] = useState(filters.search)
  const [prevFiltersSearch, setPrevFiltersSearch] = useState(filters.search)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 外部变更 filters.search（如"清除筛选"按钮）时同步回输入框。
  // 渲染期比较 props 调整 state（React 官方模式），不使用 effect，避免多余的提交
  if (prevFiltersSearch !== filters.search) {
    setPrevFiltersSearch(filters.search)
    setSearchText(filters.search)
  }

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  const handleSearchChange = (value: string) => {
    setSearchText(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => onChange({ search: value }), SEARCH_DEBOUNCE_MS)
  }

  const handleClearSearch = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    setSearchText('')
    onChange({ search: '' })
  }

  const handleFilterChange = ({ task_id, is_read }: { task_id: string; is_read: boolean | undefined }) => {
    onChange({ task_id, is_read })
  }

  return (
    <div className="space-y-3">
      {/* Search row */}
      <div className="relative flex-1 min-w-48">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
        <input
          type="text"
          aria-label="搜索标题或摘要"
          placeholder="搜索标题或摘要..."
          className="input pl-9 pr-8"
          value={searchText}
          onChange={(e) => handleSearchChange(e.target.value)}
        />
        {searchText && (
          <button
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            onClick={handleClearSearch}
            aria-label="清除搜索"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Two-row FilterBar */}
      <FilterBar
        categories={categories}
        readStatuses={DEFAULT_READ_STATUSES}
        selectedCategoryId={filters.task_id}
        selectedReadStatus={filters.is_read}
        onFilterChange={handleFilterChange}
        allCount={totalCount}
        aria-label="内容筛选"
      />

      {/* Compact extra controls — the starred toggle only makes sense once
          there is data to star, so it is hidden on an empty result set. */}
      <div className="flex items-center justify-between gap-3">
        {(totalCount ?? 0) > 0 ? (
          <label className="flex items-center gap-1.5 cursor-pointer select-none text-sm text-gray-600">
            <input
              type="checkbox"
              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              checked={filters.starred === true}
              onChange={(e) => onChange({ starred: e.target.checked ? true : undefined })}
            />
            收藏
          </label>
        ) : (
          <span />
        )}

        {/* Clear all — outlined so it reads as a real control, not faint text */}
        {filters.search || filters.task_id || filters.starred !== undefined || filters.is_read !== undefined ? (
          <button
            className="btn px-2.5 py-1 text-xs border border-gray-300 bg-white text-gray-700 shadow-sm hover:bg-gray-50 hover:border-gray-400 hover:text-gray-900"
            onClick={() => onChange({ search: '', task_id: '', starred: undefined, is_read: undefined })}
          >
            <X className="h-3.5 w-3.5" /> 清除筛选
          </button>
        ) : null}
      </div>
    </div>
  )
}

// Re-export types for consumers
export type { CategoryOption, ReadStatusOption } from './FilterBar'

export default ItemsFilterBar
