import { useRef, useCallback, forwardRef } from 'react'
import { clsx } from 'clsx'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface CategoryOption {
  id: string
  label: string
  count?: number
  unreadCount?: number
}

export interface ReadStatusOption {
  value: boolean | undefined
  label: string
  count?: number
  icon?: React.ReactNode
}

export interface FilterBarProps {
  /** Category pills - typically derived from task_name grouping */
  categories: CategoryOption[]
  /** Read status pills - presets like All/Unread/Read */
  readStatuses: ReadStatusOption[]
  /** Currently selected category id (empty string = all) */
  selectedCategoryId: string
  /** Currently selected read status value */
  selectedReadStatus: boolean | undefined
  /** Callback fired when selection changes */
  onFilterChange: (params: { task_id: string; is_read: boolean | undefined }) => void
  /** Total count for the "全部" (all) pill badge */
  allCount?: number
  /** Additional CSS classes for the root container */
  className?: string
  /** Accessibility label for the filter bar */
  'aria-label'?: string
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface PillGroupProps {
  children: React.ReactNode
  role: string
  'aria-label': string
  horizontalScrollable?: boolean
  className?: string
}

const PillGroup = forwardRef<HTMLDivElement, PillGroupProps>(function PillGroup(
  { children, role, 'aria-label': ariaLabel, horizontalScrollable = false, className },
  ref
) {
  return (
    <div
      ref={ref}
      role={role}
      aria-label={ariaLabel}
      className={clsx(
        'filter-pill-group',
        horizontalScrollable && 'filter-pill-group--scroll',
        className
      )}
    >
      {children}
    </div>
  )
})

interface PillProps {
  isActive: boolean
  onClick: () => void
  count?: number
  showBadge?: boolean
  className?: string
  'aria-pressed'?: boolean
  tabIndex?: number
  onKeyDown?: (e: React.KeyboardEvent<HTMLButtonElement>) => void
  children: React.ReactNode
}

function Pill({ isActive, onClick, count, showBadge = true, className, 'aria-pressed': ariaPressed, tabIndex, onKeyDown, children }: PillProps) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={isActive}
      aria-pressed={ariaPressed}
      tabIndex={tabIndex}
      onClick={onClick}
      onKeyDown={onKeyDown}
      className={clsx(
        'filter-pill',
        isActive && 'filter-pill--active',
        className
      )}
    >
      <span className="filter-pill__label">{children}</span>
      {showBadge && count !== undefined && count >= 0 && (
        <span className={clsx('filter-pill__badge', isActive && 'filter-pill__badge--active')}>
          {count}
        </span>
      )}
    </button>
  )
}

// ── Keyboard navigation helper ────────────────────────────────────────────────

function useKeyboardNavigation(
  options: { value: string }[],
  onSelect: (value: string) => void,
  containerRef: React.RefObject<HTMLElement | null>
) {
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>, currentValue: string) => {
      const currentIndex = options.findIndex((o) => o.value === currentValue)
      if (currentIndex === -1) return

      let nextIndex: number | null = null

      switch (e.key) {
        case 'ArrowRight':
        case 'ArrowDown':
          e.preventDefault()
          nextIndex = (currentIndex + 1) % options.length
          break
        case 'ArrowLeft':
        case 'ArrowUp':
          e.preventDefault()
          nextIndex = (currentIndex - 1 + options.length) % options.length
          break
        case 'Home':
          e.preventDefault()
          nextIndex = 0
          break
        case 'End':
          e.preventDefault()
          nextIndex = options.length - 1
          break
        default:
          return
      }

      if (nextIndex !== null) {
        const nextValue = options[nextIndex].value
        onSelect(nextValue)
        // Focus the next button after state update
        requestAnimationFrame(() => {
          const container = containerRef.current
          if (container) {
            const buttons = container.querySelectorAll<HTMLButtonElement>('[role="radio"]')
            buttons[nextIndex]?.focus()
          }
        })
      }
    },
    [options, onSelect, containerRef]
  )

  return handleKeyDown
}

// ── Main FilterBar Component ─────────────────────────────────────────────────

export function FilterBar({
  categories,
  readStatuses,
  selectedCategoryId,
  selectedReadStatus,
  onFilterChange,
  allCount,
  className,
  'aria-label': ariaLabel = 'Filter bar',
}: FilterBarProps) {
  const categoryGroupRef = useRef<HTMLDivElement>(null)
  const readStatusGroupRef = useRef<HTMLDivElement>(null)

  // Keyboard navigation for categories
  const categoryOptions = [
    { value: '' }, // "All" has empty string id
    ...categories.map((c) => ({ value: c.id })),
  ]
  const categoryKeyDown = useKeyboardNavigation(
    categoryOptions,
    (value) => onFilterChange({ task_id: value, is_read: selectedReadStatus }),
    categoryGroupRef
  )

  // Keyboard navigation for read statuses
  const readStatusOptions = readStatuses.map((rs) => ({
    value: String(rs.value ?? ''), // stringify undefined as empty string
  }))
  const readStatusKeyDown = useKeyboardNavigation(
    readStatusOptions,
    (value) =>
      onFilterChange({
        task_id: selectedCategoryId,
        is_read: value === '' ? undefined : value === 'true',
      }),
    readStatusGroupRef
  )

  // Find active category and read status indices for tabIndex management
  const categoryActiveIndex = selectedCategoryId === '' ? 0 : categories.findIndex((c) => c.id === selectedCategoryId) + 1
  const readStatusActiveIndex = readStatuses.findIndex(
    (rs) => String(rs.value ?? '') === String(selectedReadStatus ?? '')
  )

  return (
    <div className={clsx('filter-bar', className)} aria-label={ariaLabel}>
      {/* Row 1: Category pills (horizontal scrollable) */}
      <PillGroup
        ref={categoryGroupRef}
        role="radiogroup"
        aria-label="Filter by category"
        horizontalScrollable
        className="filter-bar__row filter-bar__row--categories"
      >
        {/* "All" category pill */}
        <Pill
          isActive={selectedCategoryId === ''}
          onClick={() => onFilterChange({ task_id: '', is_read: selectedReadStatus })}
          count={allCount}
          tabIndex={categoryActiveIndex === 0 ? 0 : -1}
          onKeyDown={(e) => categoryKeyDown(e, '')}
        >
          全部
        </Pill>

        {/* Category pills */}
        {categories.map((category, index) => (
          <Pill
            key={category.id}
            isActive={selectedCategoryId === category.id}
            onClick={() => onFilterChange({ task_id: category.id, is_read: selectedReadStatus })}
            count={category.count}
            tabIndex={categoryActiveIndex === index + 1 ? 0 : -1}
            onKeyDown={(e) => categoryKeyDown(e, category.id)}
          >
            {category.label}
          </Pill>
        ))}
      </PillGroup>

      {/* Row 2: Read status pills */}
      <PillGroup
        ref={readStatusGroupRef}
        role="radiogroup"
        aria-label="Filter by read status"
        className="filter-bar__row filter-bar__row--read-status"
      >
        {readStatuses.map((status, index) => (
          <Pill
            key={String(status.value ?? '')}
            isActive={String(selectedReadStatus ?? '') === String(status.value ?? '')}
            onClick={() => onFilterChange({ task_id: selectedCategoryId, is_read: status.value })}
            count={status.count}
            tabIndex={readStatusActiveIndex === index ? 0 : -1}
            onKeyDown={(e) => readStatusKeyDown(e, String(status.value ?? ''))}
            className="filter-pill--read-status"
          >
            {status.icon && <span className="filter-pill__icon">{status.icon}</span>}
            {status.label}
          </Pill>
        ))}
      </PillGroup>
    </div>
  )
}

export default FilterBar
