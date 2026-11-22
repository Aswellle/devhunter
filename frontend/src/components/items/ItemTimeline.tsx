/**
 * ItemTimeline.tsx
 * X 式侧边时间线：左侧时间轴 + 右侧事件流。
 *
 * - 分钟精度聚点：同分钟内的事件共享一个时间节点（一次采集批次
 *   天然聚成一个节点），节点高度由其事件数量撑开
 * - 年份只在每个年度区段的开头展示一次（"2026年" 圆角标签），
 *   包裹该年度范围内的全部事件
 * - 日期（M月D日）只在日期切换时展示；同一日期内后续节点只显示
 *   HH:MM，减少视觉重复
 */
import { useMemo } from 'react'
import { clsx } from 'clsx'
import type { Item } from '../../types'
import { ItemCard } from './ItemCard'

interface ItemTimelineProps {
  items: Item[]
  selectedIds: Set<string>
  onToggleSelect: (id: string) => void
}

interface TimeNode {
  key: string          // "2026-11-22 16:13"（排序与分组键）
  year: string
  month: string        // 1-12，无补零
  day: string          // 1-31，无补零
  time: string         // "16:13"
  yearChanged: boolean // 与上一个节点相比进入新年度 → 渲染年度标签
  dateChanged: boolean // 与上一个节点相比日期变化 → 渲染 M月D日
  items: Item[]
}

const pad2 = (n: number) => String(n).padStart(2, '0')

function buildNodes(items: Item[]): TimeNode[] {
  const sorted = [...items].sort(
    (a, b) => new Date(b.fetched_at).getTime() - new Date(a.fetched_at).getTime(),
  )
  const map = new Map<string, Item[]>()
  const order: string[] = []
  for (const item of sorted) {
    const d = new Date(item.fetched_at)
    // 无效时间兜底归入"未知时间"节点，绝不丢条目
    const key = Number.isNaN(d.getTime())
      ? '?'
      : `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
    if (!map.has(key)) {
      map.set(key, [])
      order.push(key)
    }
    map.get(key)!.push(item)
  }
  // 年/日切换标记在数据层算好：React Compiler 禁止渲染期改写外层变量
  let prevYear: string | null = null
  let prevDate: string | null = null
  return order.map((key) => {
    let year = '?'
    let month = ''
    let day = ''
    let time = '未知时间'
    if (key !== '?') {
      const [datePart, timePart] = key.split(' ')
      const [y, m, dd] = datePart.split('-')
      year = y
      month = String(Number(m))
      day = String(Number(dd))
      time = timePart
    }
    const dateKey = `${year}-${month}-${day}`
    const yearChanged = year !== prevYear
    const dateChanged = prevDate !== dateKey
    prevYear = year
    prevDate = dateKey
    return {
      key,
      year,
      month,
      day,
      time,
      yearChanged,
      dateChanged,
      items: map.get(key)!,
    }
  })
}

export function ItemTimeline({ items, selectedIds, onToggleSelect }: ItemTimelineProps) {
  const nodes = useMemo(() => buildNodes(items), [items])

  return (
    <div className="relative px-4 py-3">
      {/* 纵向时间轴主线：穿过每个节点圆心（时间列 64px + 间距 12px + 圆心 5px） */}
      <div
        className="absolute top-4 bottom-6 w-px bg-gray-200"
        style={{ left: 'calc(1rem + 64px + 12px + 4px)' }}
        aria-hidden="true"
      />
      {nodes.map((node) => {
        const hasUnread = node.items.some((i) => !i.is_read)

        return (
          <div key={node.key}>
            {node.yearChanged && (
              <div className="flex items-center mb-2 -ml-1">
                <span className="text-xs font-semibold text-gray-500 bg-gray-100 rounded-full px-3 py-0.5">
                  {node.year === '?' ? '时间未知' : `${node.year}年`}
                </span>
              </div>
            )}
            <div className="flex gap-3">
              {/* 时间标签：日期切换时展示 M月D日，其余只显示 HH:MM */}
              <div className="w-16 shrink-0 text-right pt-0.5">
                {node.dateChanged && (
                  <div className="text-[11px] font-medium text-gray-500 leading-tight">
                    {node.month}月{node.day}日
                  </div>
                )}
                <div className="text-xs text-gray-400 font-mono leading-tight">
                  {node.time}
                </div>
              </div>
              {/* 轴上圆点：有未读用主题色，否则灰色 */}
              <div className="relative z-10 flex flex-col items-center shrink-0 pt-1">
                <span
                  className={clsx(
                    'block w-[9px] h-[9px] rounded-full ring-4 ring-white',
                    hasUnread ? 'bg-primary-500' : 'bg-gray-300',
                  )}
                  aria-hidden="true"
                />
              </div>
              {/* 同一分钟的条目堆叠在节点右侧 */}
              <div className="flex-1 min-w-0 space-y-2 pb-4">
                {node.items.map((item) => {
                  const selected = selectedIds.has(item.id)
                  return (
                    <div key={item.id} className="flex items-start gap-0">
                      <div
                        role="checkbox"
                        aria-checked={selected}
                        aria-label={`${selected ? '取消选择' : '选择'}: ${item.title}`}
                        tabIndex={0}
                        onClick={() => onToggleSelect(item.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            onToggleSelect(item.id)
                          }
                        }}
                        className={clsx(
                          'self-stretch flex items-center px-1.5 shrink-0 transition-colors cursor-pointer rounded-l-md',
                          selected
                            ? 'text-primary-600 bg-primary-50 hover:bg-primary-100'
                            : 'text-gray-300 hover:text-primary-500 hover:bg-gray-50',
                          'focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1',
                        )}
                      >
                        <div
                          className={clsx(
                            'h-4 w-4 rounded border-2 flex items-center justify-center transition-colors',
                            selected ? 'border-primary-600 bg-primary-600' : 'border-current',
                          )}
                        >
                          {selected && (
                            <svg className="h-2.5 w-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                            </svg>
                          )}
                        </div>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="[&>.card]:shadow-none [&>.card]:rounded-none [&>.card]:border-0 [&>.card]:border-b [&>.card]:border-gray-100">
                          <ItemCard item={item} />
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
