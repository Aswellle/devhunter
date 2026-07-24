import { Search, X, Eye, EyeOff } from 'lucide-react'
import { clsx } from 'clsx'
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
  /** Use the new two-row FilterBar layout (default: false for backward compatibility) */
  useNewLayout?: boolean
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

// ── New layout: Two-row FilterBar ─────────────────────────────────────────────

interface FilterBarLayoutProps {
  filters: FiltersState
  onChange: (f: Partial<FiltersState>) => void
  tasks: Task[]
  categoryCounts?: Record<string, { total: number; unread: number }>
  /** Total item count (from API response) for the "全部" pill badge */
  totalCount?: number
}

function FilterBarLayout({ filters, onChange, tasks, categoryCounts, totalCount }: FilterBarLayoutProps) {
  const categories = tasksToCategories(tasks, categoryCounts)

  // Map read status with counts if available
  const readStatuses: ReadStatusOption[] = DEFAULT_READ_STATUSES.map((status) => ({
    ...status,
    // In a real implementation, you would calculate these from the full items list
    // For now, we pass undefined counts - the parent can provide them if needed
  }))

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
          placeholder="搜索标题或摘要..."
          className="input pl-9 pr-8"
          value={filters.search}
          onChange={(e) => onChange({ search: e.target.value })}
        />
        {filters.search && (
          <button
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            onClick={() => onChange({ search: '' })}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Two-row FilterBar */}
      <FilterBar
        categories={categories}
        readStatuses={readStatuses}
        selectedCategoryId={filters.task_id}
        selectedReadStatus={filters.is_read}
        onFilterChange={handleFilterChange}
        allCount={totalCount}
        aria-label="Items filter bar"
      />

      {/* Compact extra controls (starred toggle) */}
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-1.5 cursor-pointer select-none text-sm text-gray-600">
          <input
            type="checkbox"
            className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            checked={filters.starred === true}
            onChange={(e) => onChange({ starred: e.target.checked ? true : undefined })}
          />
          收藏
        </label>

        {/* Clear all button */}
        {filters.search || filters.task_id || filters.starred !== undefined || filters.is_read !== undefined ? (
          <button
            className="btn-ghost text-xs"
            onClick={() => onChange({ search: '', task_id: '', starred: undefined, is_read: undefined })}
          >
            <X className="h-3.5 w-3.5" /> 清除
          </button>
        ) : null}
      </div>
    </div>
  )
}

// ── Legacy single-row layout (original implementation) ────────────────────────

function LegacyLayout({ filters, onChange, tasks }: Omit<ItemsFilterBarProps, 'useNewLayout'>) {
  const hasActiveFilters = filters.search || filters.task_id || filters.starred !== undefined || filters.is_read !== undefined

  const clearAll = () => onChange({ search: '', task_id: '', starred: undefined, is_read: undefined })

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Search box */}
      <div className="relative flex-1 min-w-48">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
        <input
          type="text"
          placeholder="搜索标题或摘要..."
          className="input pl-9 pr-8"
          value={filters.search}
          onChange={(e) => onChange({ search: e.target.value })}
        />
        {filters.search && (
          <button
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            onClick={() => onChange({ search: '' })}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Source filter dropdown */}
      <div className="relative">
        <select
          className="input w-auto min-w-32 pr-8 appearance-none bg-white"
          value={filters.task_id}
          onChange={(e) => onChange({ task_id: e.target.value })}
        >
          <option value="">全部数据源</option>
          {tasks.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
        <span className="absolute right-2 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none">
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </span>
      </div>

      {/* Quick filter: read/unread */}
      <div className="flex items-center gap-1 rounded-md border border-gray-200 p-0.5 bg-white">
        <button
          onClick={() => onChange({ is_read: filters.is_read === false ? undefined : false })}
          className={clsx(
            'flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors',
            filters.is_read === false
              ? 'bg-primary-600 text-white shadow-sm'
              : 'text-gray-600 hover:bg-gray-100'
          )}
        >
          <EyeOff className="h-3.5 w-3.5" />
          未读
        </button>
        <button
          onClick={() => onChange({ is_read: filters.is_read === true ? undefined : true })}
          className={clsx(
            'flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors',
            filters.is_read === true
              ? 'bg-primary-600 text-white shadow-sm'
              : 'text-gray-600 hover:bg-gray-100'
          )}
        >
          <Eye className="h-3.5 w-3.5" />
          已读
        </button>
      </div>

      {/* Starred filter */}
      <label className="flex items-center gap-1.5 cursor-pointer select-none text-sm text-gray-600">
        <input
          type="checkbox"
          className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
          checked={filters.starred === true}
          onChange={(e) => onChange({ starred: e.target.checked ? true : undefined })}
        />
        收藏
      </label>

      {/* Reset */}
      {hasActiveFilters && (
        <button
          className="btn-ghost text-xs"
          onClick={clearAll}
        >
          <X className="h-3.5 w-3.5" /> 清除
        </button>
      )}
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────

export function ItemsFilterBar({ filters, onChange, tasks, categoryCounts, totalCount, useNewLayout = false }: ItemsFilterBarProps) {
  if (useNewLayout) {
    return (
      <FilterBarLayout
        filters={filters}
        onChange={onChange}
        tasks={tasks}
        categoryCounts={categoryCounts}
        totalCount={totalCount}
      />
    )
  }

  return (
    <LegacyLayout
      filters={filters}
      onChange={onChange}
      tasks={tasks}
    />
  )
}

// Re-export types for consumers
export type { CategoryOption, ReadStatusOption } from './FilterBar'

export default ItemsFilterBar
