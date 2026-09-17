import { useState, useMemo, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { ChevronDown, ChevronRight, CheckCheck, Check, Star, Rss, Trash2, X, Layers } from 'lucide-react'
import { clsx } from 'clsx'
import { itemsApi } from '../api/items'
import { queryKeys } from '../api/queryKeys'
import { tasksApi } from '../api/tasks'
import { threadsApi } from '../api/threads'
import { ItemCard } from '../components/items/ItemCard'
import { ItemsFilterBar } from '../components/items/ItemsFilterBar'
import { ThreadCard } from '../components/items/ThreadCard'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'
import { SkeletonList } from '../components/ui/Skeleton'
import { toast } from 'react-hot-toast'
import type { Item, ThreadWithItems } from '../types'

type ViewMode = 'source' | 'thread'

interface Filters {
  search: string
  task_id: string
  starred: boolean | undefined
  is_read: boolean | undefined
  [key: string]: unknown
}

interface GroupedItems {
  task_id: string
  task_name: string
  items: Item[]
  unreadCount: number
  latestFetchedAt: string
}

export function ItemsPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const [filters, setFilters] = useState<Filters>({
    search: searchParams.get('search') || '',
    task_id: searchParams.get('task_id') || '',
    starred: searchParams.get('starred') === 'true' ? true : searchParams.get('starred') === 'false' ? false : undefined,
    is_read: searchParams.get('is_read') === 'true' ? true : searchParams.get('is_read') === 'false' ? false : undefined,
  })
  const [viewMode, setViewMode] = useState<ViewMode>((searchParams.get('view') as ViewMode) || 'source')
  // Sync filter state to URL
  useEffect(() => {
    const params = new URLSearchParams()
    if (filters.search) params.set('search', filters.search)
    if (filters.task_id) params.set('task_id', filters.task_id)
    if (filters.starred !== undefined) params.set('starred', String(filters.starred))
    if (filters.is_read !== undefined) params.set('is_read', String(filters.is_read))
    if (viewMode !== 'source') params.set('view', viewMode)
    setSearchParams(params, { replace: true })
  }, [filters, viewMode, setSearchParams])

  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  // U9: replaces window.confirm() for batch delete — a blocking native
  // dialog with no visual consistency with the rest of the app. Two-step
  // inline confirm: first click arms it, second click within the window
  // actually deletes; clicking elsewhere or 4s of inactivity disarms it.
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  // U9: 4s inactivity timer — disarms the confirm state so a half-finished
  // batch action can't linger. Reset on every state change via the effect's
  // dependency; cleared on unmount or when the user confirms/cancels.
  useEffect(() => {
    if (!confirmingDelete) return
    const id = setTimeout(() => setConfirmingDelete(false), 8000)
    return () => clearTimeout(id)
  }, [confirmingDelete])

  const qc = useQueryClient()

  // Fetch items
  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: queryKeys.items.grouped(filters),
    queryFn: () =>
      itemsApi.list({
        search: filters.search || undefined,
        task_id: filters.task_id || undefined,
        starred: filters.starred,
        is_read: filters.is_read,
        per_page: 100,
      }),
  })

  // Fetch tasks for filter bar
  const { data: tasksPage } = useQuery({
    queryKey: queryKeys.tasks.all,
    queryFn: () => tasksApi.list({ per_page: 100 }),
  })

  // Fetch counts for filter bar badges (independent of item list pagination)
  const { data: countsData } = useQuery({
    queryKey: queryKeys.items.counts(),
    queryFn: itemsApi.counts,
    staleTime: 30_000,
  })

  // Fetch Threads (only when in thread view)
  const { data: threadsPage } = useQuery({
    queryKey: queryKeys.threads.list({ task_id: filters.task_id }),
    queryFn: () =>
      threadsApi.list({
        task_id: filters.task_id || undefined,
        per_page: 50,
      }),
    enabled: viewMode === 'thread',
  })

  // Compute category counts from dedicated counts API (stable across filter changes)
  const categoryCounts = useMemo<Record<string, { total: number; unread: number }>>(() => {
    return countsData?.by_task || {}
  }, [countsData])

  // Group items by task_id
  const groupedItems = useMemo<GroupedItems[]>(() => {
    if (!data?.items) return []
    if (filters.task_id) {
      const items = [...data.items].sort(
        (a, b) => new Date(b.fetched_at).getTime() - new Date(a.fetched_at).getTime()
      )
      return [{
        task_id: filters.task_id,
        task_name: items[0]?.task_name || tasksPage?.items.find(t => t.id === filters.task_id)?.name || 'Unknown',
        items,
        unreadCount: items.filter(i => !i.is_read).length,
        latestFetchedAt: items[0]?.fetched_at ?? '',
      }]
    }
    const groups = new Map<string, GroupedItems>()
    for (const item of data.items) {
      const key = item.task_id || 'unknown'
      if (!groups.has(key)) {
        groups.set(key, {
          task_id: key,
          task_name: item.task_name || 'Unknown Source',
          items: [],
          unreadCount: 0,
          latestFetchedAt: item.fetched_at,
        })
      }
      const group = groups.get(key)!
      group.items.push(item)
      if (!item.is_read) group.unreadCount++
      if (new Date(item.fetched_at) > new Date(group.latestFetchedAt)) {
        group.latestFetchedAt = item.fetched_at
      }
    }
    return Array.from(groups.values())
      .sort((a, b) =>
        new Date(b.latestFetchedAt).getTime() - new Date(a.latestFetchedAt).getTime()
      )
      .map(g => ({
        ...g,
        items: [...g.items].sort((a, b) =>
          new Date(b.fetched_at).getTime() - new Date(a.fetched_at).getTime()
        ),
      }))
  }, [data, filters.task_id, tasksPage])

  const toggleGroup = useCallback((taskId: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev)
      if (next.has(taskId)) next.delete(taskId)
      else next.add(taskId)
      return next
    })
  }, [])

  const expandGroup = useCallback((taskId: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev)
      next.delete(taskId)
      return next
    })
  }, [])

  const toggleSelect = useCallback((itemId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(itemId)) next.delete(itemId)
      else next.add(itemId)
      return next
    })
  }, [])

  const selectAllInGroup = useCallback((group: GroupedItems) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      const allUnreadInGroup = group.items.filter(i => !i.is_read).map(i => i.id)
      const allSelected = allUnreadInGroup.every(id => prev.has(id))
      if (allSelected) {
        allUnreadInGroup.forEach(id => next.delete(id))
      } else {
        allUnreadInGroup.forEach(id => next.add(id))
      }
      return next
    })
  }, [])

  // F3: 乐观更新 + 回滚
  const batchStarMutation = useMutation({
    mutationFn: ({ ids, starred }: { ids: string[]; starred: boolean }) =>
      itemsApi.batchPatch(ids, { is_starred: starred }),
    onMutate: async ({ ids, starred }) => {
      // 取消正在进行的查询，避免覆盖乐观更新
      await qc.cancelQueries({ queryKey: queryKeys.items.all })
      // 保存当前状态用于回滚
      const previousData = qc.getQueryData(queryKeys.items.grouped(filters))
      // 乐观更新：立即修改缓存
      qc.setQueryData(queryKeys.items.grouped(filters), (old: unknown) => {
        if (!old || typeof old !== 'object' || !('items' in old)) return old
        const o = old as { items: Array<Record<string, unknown>> }
        const idSet = new Set(ids)
        return {
          ...o,
          items: o.items.map((item) =>
            idSet.has(item.id as string) ? { ...item, is_starred: starred } : item
          ),
        }
      })
      return { previousData }
    },
    onError: (_err, _vars, context) => {
      // 回滚到变更前的状态
      if (context?.previousData) {
        qc.setQueryData(queryKeys.items.grouped(filters), context.previousData)
      }
      toast.error('操作失败', { duration: 5000 })
    },
    onSuccess: (result) => {
      toast.success(`${batchStarMutation.variables?.starred ? '已收藏' : '已取消收藏'} ${result.updated} 条`)
      setSelectedIds(new Set())
    },
    onSettled: () => {
      // 最终与服务端同步
      qc.invalidateQueries({ queryKey: queryKeys.items.all })
      qc.invalidateQueries({ queryKey: queryKeys.threads.all })
      qc.invalidateQueries({ queryKey: queryKeys.recommendations.all })
    },
  })

  // F3: 乐观更新 + 回滚
  const batchDeleteMutation = useMutation({
    mutationFn: (ids: string[]) => itemsApi.batchDelete(ids),
    onMutate: async (ids) => {
      await qc.cancelQueries({ queryKey: queryKeys.items.all })
      const previousData = qc.getQueryData(queryKeys.items.grouped(filters))
      qc.setQueryData(queryKeys.items.grouped(filters), (old: unknown) => {
        if (!old || typeof old !== 'object' || !('items' in old)) return old
        const o = old as { items: Array<Record<string, unknown>> }
        const idSet = new Set(ids)
        return { ...o, items: o.items.filter((item) => !idSet.has(item.id as string)) }
      })
      return { previousData }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        qc.setQueryData(queryKeys.items.grouped(filters), context.previousData)
      }
      toast.error('删除失败', { duration: 5000 })
    },
    onSuccess: (result) => {
      toast.success(`已删除 ${result.deleted} 条`)
      setSelectedIds(new Set())
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: queryKeys.items.all })
      qc.invalidateQueries({ queryKey: queryKeys.threads.all })
      qc.invalidateQueries({ queryKey: queryKeys.recommendations.all })
    },
  })

  // F3: 乐观更新 + 回滚
  const batchMarkReadMutation = useMutation({
    mutationFn: (ids: string[]) => itemsApi.batchPatch(ids, { is_read: true }),
    onMutate: async (ids) => {
      await qc.cancelQueries({ queryKey: queryKeys.items.all })
      const previousData = qc.getQueryData(queryKeys.items.grouped(filters))
      qc.setQueryData(queryKeys.items.grouped(filters), (old: unknown) => {
        if (!old || typeof old !== 'object' || !('items' in old)) return old
        const o = old as { items: Array<Record<string, unknown>> }
        const idSet = new Set(ids)
        return {
          ...o,
          items: o.items.map((item) =>
            idSet.has(item.id as string) ? { ...item, is_read: true } : item
          ),
        }
      })
      return { previousData }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        qc.setQueryData(queryKeys.items.grouped(filters), context.previousData)
      }
      toast.error('操作失败', { duration: 5000 })
    },
    onSuccess: (result) => {
      toast.success(`已标记 ${result.updated} 条为已读`)
      setSelectedIds(new Set())
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: queryKeys.items.all })
      qc.invalidateQueries({ queryKey: queryKeys.threads.all })
      qc.invalidateQueries({ queryKey: queryKeys.recommendations.all })
    },
  })

  const handleFilterChange = (partial: Partial<Filters>) => {
    setFilters(f => {
      const next = { ...f, ...partial }
      if (partial.task_id && partial.task_id !== f.task_id) {
        expandGroup(partial.task_id)
      }
      if (partial.task_id === '' && f.task_id !== '') {
        setCollapsedGroups(new Set())
      }
      return next
    })
  }

  // U13: previously rebuilt on every render (including unrelated state
  // changes like filter/collapse toggles) since it ran directly in the
  // render body instead of behind useMemo. Declared before the callbacks
  // below so handleBatchMarkRead can read it without a use-before-define.
  const selectedUnreadIds = useMemo(
    () =>
      new Set(
        [...selectedIds].filter(id => {
          const item = data?.items.find(i => i.id === id)
          return item && !item.is_read
        })
      ),
    [selectedIds, data?.items]
  )
  const totalSelected = selectedIds.size
  const hasUnreadSelected = selectedUnreadIds.size > 0

  const handleBatchStar = () => {
    const selected = Array.from(selectedIds)
    const firstSelected = data?.items.find(i => selectedIds.has(i.id))
    const newStarred = !firstSelected?.is_starred
    batchStarMutation.mutate({ ids: selected, starred: newStarred })
  }

  const handleBatchMarkRead = () => {
    batchMarkReadMutation.mutate(Array.from(selectedUnreadIds))
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6">

      {/* Page header */}
      <div className="mb-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">采集结果</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {viewMode === 'source'
                ? (data
                    ? filters.task_id
                      ? `共 ${data.total} 条记录`
                      : `共 ${groupedItems.length} 个数据源，${data.total} 条记录`
                    : '加载中...')
                : (threadsPage
                    ? `共 ${threadsPage.total} 个热点 Thread`
                    : '加载中...')}
            </p>
          </div>

          {/* View mode toggle */}
          <div className="flex items-center gap-1 p-1 bg-gray-100 rounded-lg">
            <button
              onClick={() => setViewMode('source')}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all',
                viewMode === 'source'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              )}
            >
              <Rss className="h-4 w-4" />
              数据源
            </button>
            <button
              onClick={() => setViewMode('thread')}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all',
                viewMode === 'thread'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              )}
            >
              <Layers className="h-4 w-4" />
              热点聚合
            </button>
          </div>
        </div>
      </div>

      {/* Filter bar */}
      <div className="mb-4">
        <ItemsFilterBar
          filters={filters}
          onChange={handleFilterChange}
          tasks={tasksPage?.items ?? []}
          categoryCounts={categoryCounts}
          totalCount={countsData?.total ?? data?.total}
          useNewLayout={true}
        />
      </div>

      {/* Content */}
      {viewMode === 'thread' ? (
        /* ── Thread View ── */
        isFetching && !threadsPage ? (
          <div className="flex justify-center py-12">
            <Spinner />
          </div>
        ) : threadsPage?.items && threadsPage.items.length > 0 ? (
          <div className="space-y-3">
            {(threadsPage.items as ThreadWithItems[]).map((thread) => (
              <ThreadCard
                key={thread.id}
                thread={thread as ThreadWithItems}
                defaultExpanded={false}
              />
            ))}
          </div>
        ) : (
          <Empty
            title="暂无热点聚合"
            description="采集更多内容后，系统会自动将讨论同一事件的内容聚合为 Thread"
          />
        )
      ) : (
        /* ── Source View (original) ── */
        // U1: guard the initial fetch — without `isFetching && !data`, a
        // first-time user sees the "no items yet, go create a task" empty
        // state flash before data has even arrived, which reads as if the
        // app already checked and found nothing.
        // U3: surface isError with a retry action instead of silently
        // rendering the same empty state as "no data" on a failed request.
        isFetching && !data ? (
          <div className="max-w-4xl mx-auto px-4 sm:px-6">
            <SkeletonList count={5} />
          </div>
        ) : isError ? (
          <Empty
            title="加载失败"
            description="采集结果加载出错，请检查网络连接后重试"
            action={
              <button onClick={() => refetch()} className="btn-primary">
                重试
              </button>
            }
          />
        ) : groupedItems.length === 0 ? (
          <Empty
            title="暂无采集结果"
            description={
              filters.search || filters.task_id || filters.starred
                ? '当前筛选条件无匹配结果'
                : '前往「任务管理」创建采集任务，系统将自动抓取数据'
            }
            action={
              filters.search || filters.task_id || filters.starred ? (
                <button
                  onClick={() => setFilters({ search: '', task_id: '', starred: undefined, is_read: undefined })}
                  className="btn-ghost"
                >
                  清除筛选
                </button>
              ) : undefined
            }
          />
        ) : (
          <>
            <div className="space-y-3">
              {groupedItems.map(group => {
                const isCollapsed = collapsedGroups.has(group.task_id)
                const someSelected = group.items.filter(i => !i.is_read).some(i => selectedIds.has(i.id))

                return (
                  <div key={group.task_id} className="card overflow-hidden">
                    {/* Group header */}
                    <button
                      onClick={() => toggleGroup(group.task_id)}
                      className={clsx(
                        'w-full flex items-center gap-3 px-4 py-3 text-left transition-colors',
                        'hover:bg-gray-50',
                        isCollapsed && 'bg-gray-50/50'
                      )}
                    >
                      <span className="text-gray-400">
                        {isCollapsed
                          ? <ChevronRight className="h-5 w-5" />
                          : <ChevronDown className="h-5 w-5" />
                        }
                      </span>
                      <Rss className="h-4 w-4 text-primary-500 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-900 truncate">
                            {group.task_name}
                          </span>
                          {group.unreadCount > 0 && (
                            <span className="badge badge-primary">
                              {group.unreadCount} 未读
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-gray-400 mt-0.5">
                          {group.items.length} 条内容
                          {filters.search && (
                            <span className="ml-1">（搜索: "{filters.search}"）</span>
                          )}
                        </div>
                      </div>
                      {!isCollapsed && group.unreadCount > 0 && (
                        // span (not button) to avoid invalid nested-button HTML inside the
                        // group header <button>. role="button" + keyboard handler keeps it
                        // accessible; stopPropagation so the header's toggle doesn't fire.
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={(e) => {
                            e.stopPropagation()
                            selectAllInGroup(group)
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault()
                              e.stopPropagation()
                              selectAllInGroup(group)
                            }
                          }}
                          className={clsx(
                            'p-1.5 rounded transition-colors shrink-0 cursor-pointer',
                            someSelected
                              ? 'text-primary-600 bg-primary-50 hover:bg-primary-100'
                              : 'text-gray-400 hover:text-primary-600 hover:bg-gray-100'
                          )}
                          title="全选未读"
                        >
                          <CheckCheck className="h-4 w-4" />
                        </span>
                      )}
                    </button>

                    {!isCollapsed && (
                      <div className="border-t border-gray-100">
                        {someSelected && (
                          <div className="px-4 py-2 bg-primary-50 border-b border-primary-100 flex items-center gap-2 text-xs text-primary-700">
                            <span>已选择 {group.items.filter(i => !i.is_read && selectedIds.has(i.id)).length} 条</span>
                            <button
                              onClick={() => setSelectedIds(prev => {
                                const next = new Set(prev)
                                group.items.forEach(i => next.delete(i.id))
                                return next
                              })}
                              className="underline hover:no-underline"
                            >
                              清除
                            </button>
                          </div>
                        )}
                        <div className="divide-y divide-gray-100">
                          {group.items.map(item => (
                            <div key={item.id} className="flex items-start gap-0">
                              <div
                                role="checkbox"
                                aria-checked={selectedIds.has(item.id)}
                                aria-label={`${selectedIds.has(item.id) ? '取消选择' : '选择'}: ${item.title}`}
                                tabIndex={0}
                                onClick={() => toggleSelect(item.id)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault()
                                    toggleSelect(item.id)
                                  }
                                }}
                                className={clsx(
                                  'p-3 shrink-0 transition-colors cursor-pointer rounded',
                                  selectedIds.has(item.id)
                                    ? 'text-primary-600 bg-primary-50 hover:bg-primary-100'
                                    : 'text-gray-300 hover:text-primary-500 hover:bg-gray-50',
                                  'focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1'
                                )}
                              >
                                <div className={clsx(
                                  'h-4 w-4 rounded border-2 flex items-center justify-center transition-colors',
                                  selectedIds.has(item.id)
                                    ? 'border-primary-600 bg-primary-600'
                                    : 'border-current'
                                )}>
                                  {selectedIds.has(item.id) && (
                                    <svg className="h-2.5 w-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                    </svg>
                                  )}
                                </div>
                              </div>

                              <div className="flex-1 min-w-0 pl-0">
                                <ItemCard item={item} />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Batch actions bar */}
            {totalSelected > 0 && (
              <div className="sticky bottom-4 z-30 flex justify-center pt-4">
                <div className="flex items-center gap-3 px-4 py-3 bg-gray-900 text-white rounded-xl shadow-2xl">
                  <span className="text-sm font-medium">
                    已选择 <b>{totalSelected}</b> 条
                  </span>
                  <div className="w-px h-5 bg-gray-700" />
                  {hasUnreadSelected && (
                    <>
                      <button
                        onClick={handleBatchMarkRead}
                        disabled={batchMarkReadMutation.isPending}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-blue-900 hover:bg-blue-800 text-blue-200 transition-colors disabled:opacity-50"
                      >
                        <Check className="h-4 w-4" />
                        标记已读
                      </button>
                      <div className="w-px h-5 bg-gray-700" />
                    </>
                  )}

                  <button
                    onClick={handleBatchStar}
                    disabled={batchStarMutation.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-gray-800 hover:bg-gray-700 transition-colors disabled:opacity-50"
                  >
                    <Star className="h-4 w-4" />
                    {data?.items.find(i => selectedIds.has(i.id))?.is_starred ? '取消收藏' : '收藏'}
                  </button>
                  {confirmingDelete ? (

                    <button
                      onClick={() => {
                        setConfirmingDelete(false)
                        batchDeleteMutation.mutate(Array.from(selectedIds))
                      }}
                      onBlur={() => setConfirmingDelete(false)}
                      autoFocus
                      disabled={batchDeleteMutation.isPending}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-500 text-white transition-colors disabled:opacity-50"
                    >
                      <Trash2 className="h-4 w-4" />
                      确认删除 {totalSelected} 条
                    </button>
                  ) : (
                    <button
                      onClick={() => setConfirmingDelete(true)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-gray-800 hover:bg-gray-700 text-red-300 transition-colors"
                    >
                      <Trash2 className="h-4 w-4" />
                      删除
                    </button>
                  )}
                  <button
                    onClick={() => {
                      setConfirmingDelete(false)
                      setSelectedIds(new Set())
                    }}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </>
        )
      )}
    </div>
  )
}
