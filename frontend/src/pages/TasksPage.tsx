import { useCallback, useState } from 'react'
import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus, LayoutGrid } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { queryKeys } from '../api/queryKeys'
import { TaskCard } from '../components/tasks/TaskCard'
import { TaskFormModal } from '../components/tasks/TaskFormModal'
import { SourceWizard } from '../components/tasks/SourceWizard'
import { TemplateMarket } from '../components/tasks/TemplateMarket'
import { ExecutionHistoryPanel } from '../components/tasks/ExecutionHistoryPanel'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'
import type { Task } from '../types'

const STATUS_TABS = [
  { label: '全部', value: '' },
  { label: '运行中', value: 'active' },
  { label: '已暂停', value: 'paused' },
  { label: '错误', value: 'error' },
] as const

export function TasksPage() {
  const [showForm, setShowForm]         = useState(false)
  const [editTaskId, setEditTaskId]     = useState<string | null>(null)
  const [historyTask, setHistoryTask]   = useState<Task | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [showWizard, setShowWizard]     = useState(false)
  const [showMarket, setShowMarket]     = useState(false)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: queryKeys.tasks.list({ status: statusFilter || undefined }),
    queryFn: () => tasksApi.list({ status: statusFilter || undefined, per_page: 100 }),
    refetchInterval: (query) => {
      // 上一次拉取失败时暂停自动轮询（错误 UI 已提供重试按钮，重试成功后自动恢复）。
      // 之前用 errorUpdateCount（累计值，成功不清零），一次网络抖动会永久关闭轮询
      if (query.state.status === 'error') return false
      return 15000
    },
    // Keep the previous tab's list visible while a tab switch refetches —
    // previously every tab change flashed the full-page spinner.
    placeholderData: (prev) => prev,
  })

  // Fetch full task details when opening edit modal (list API returns TaskListItem with fewer fields)
  const { data: editTaskFull, isFetching: isEditTaskLoading } = useQuery({
    queryKey: queryKeys.tasks.detail(editTaskId ?? ''),
    queryFn: () => tasksApi.get(editTaskId!),
    enabled: !!editTaskId,
  })

  const handleEdit = useCallback((task: Task) => {
    setEditTaskId(task.id)
    setShowForm(true)
  }, [])

  // 稳定引用：TaskFormModal 的 useModalA11y 依赖 onClose，每次渲染都换新函数
  // 会导致模态内的 effect 重跑、把焦点抢回第一个可聚焦元素（打断正在输入的用户）
  const handleCloseForm = useCallback(() => {
    setShowForm(false)
    setEditTaskId(null)
  }, [])

  // tablist 方向键导航（roving tabindex）：←/→ 在状态 tab 间移动焦点并切换
  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    e.preventDefault()
    const currentIndex = STATUS_TABS.findIndex((t) => t.value === statusFilter)
    const nextIndex = e.key === 'ArrowRight'
      ? (currentIndex + 1) % STATUS_TABS.length
      : (currentIndex - 1 + STATUS_TABS.length) % STATUS_TABS.length
    setStatusFilter(STATUS_TABS[nextIndex].value)
    const tabButtons = e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
    tabButtons?.[nextIndex]?.focus()
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-semibold">任务管理</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowMarket(true)}
            className="btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-sm"
          >
            <LayoutGrid className="h-4 w-4" />
            模板市场
          </button>
          <button
            onClick={() => setShowWizard(true)}
            className="btn-primary flex items-center gap-1.5 px-3 py-1.5 text-sm"
          >
            <Plus className="h-4 w-4" />
            添加数据源
          </button>
        </div>
      </div>

      {/* Status filter tabs */}
      <div role="tablist" aria-label="任务状态筛选" className="flex gap-1 mb-5 border-b border-gray-200">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            role="tab"
            aria-selected={statusFilter === tab.value}
            tabIndex={statusFilter === tab.value ? 0 : -1}
            onKeyDown={handleTabKeyDown}
            onClick={() => setStatusFilter(tab.value)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 ${
              statusFilter === tab.value
                ? 'border-primary-600 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>


      {/* Content */}
      {isError ? (
        // A failed fetch must not masquerade as "暂无采集任务" — show an
        // explicit error state with retry.
        <Empty
          title="任务加载失败"
          description="任务列表加载出错，请检查网络连接后重试"
          action={
            <button className="btn-primary" onClick={() => refetch()}>
              重试
            </button>
          }
        />
      ) : isLoading ? (
        <div className="flex justify-center py-20">
          <Spinner className="h-8 w-8" />
        </div>
      ) : !data?.items.length ? (
        <Empty
          title="暂无采集任务"
          description="点击「新建任务」开始配置你的第一个数据源"
          action={
            <button className="btn-primary" onClick={() => setShowForm(true)}>
              <Plus className="h-4 w-4" /> 新建任务
            </button>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
          {data.items.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              onEdit={handleEdit}
              onViewHistory={setHistoryTask}
            />
          ))}
        </div>
      )}

      {/* Modals */}
      {/* U5: when editing, editTaskId is set immediately but the full task
          fetch is still in flight — rendering TaskFormModal right away with
          task={editTaskFull ?? null} showed a blank "create task" form for
          a moment before the real data arrived and the form suddenly
          populated. Wait for the fetch when we're editing an existing task;
          creating a new one has no such fetch, so it still opens instantly. */}
      {showForm && editTaskId && isEditTaskLoading && createPortal(
        <div role="dialog" aria-modal="true" aria-label="加载中" className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50">
          <Spinner className="h-8 w-8" />
        </div>,
        document.body
      )}
      {showForm && (!editTaskId || !isEditTaskLoading) && createPortal(
        // key 确保切换“新建/编辑不同任务”时组件重新挂载，表单按目标任务重新初始化
        <TaskFormModal key={editTaskId ?? 'create'} task={editTaskFull ?? null} onClose={handleCloseForm} />,
        document.body
      )}
      {/* ✅ 修复：Portal 渲染，不受 overflow:hidden 容器影响 */}
      {historyTask && createPortal(
        <ExecutionHistoryPanel task={historyTask} onClose={() => setHistoryTask(null)} />,
        document.body
      )}
      {showWizard && createPortal(
        <SourceWizard onClose={() => setShowWizard(false)} onCreated={() => setShowWizard(false)} />,
        document.body
      )}
      {showMarket && createPortal(
        <TemplateMarket onClose={() => setShowMarket(false)} onCreated={() => setShowMarket(false)} />,
        document.body
      )}
    </div>
  )
}
