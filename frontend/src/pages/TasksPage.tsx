import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus, LayoutGrid } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { TaskCard } from '../components/tasks/TaskCard'
import { TaskFormModal } from '../components/tasks/TaskFormModal'
import { SourceWizard } from '../components/tasks/SourceWizard'
import { TemplateMarket } from '../components/tasks/TemplateMarket'
import { ExecutionHistoryPanel } from '../components/tasks/ExecutionHistoryPanel'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'
import type { Task } from '../types'
export function TasksPage() {
  const [showForm, setShowForm]         = useState(false)
  const [editTaskId, setEditTaskId]     = useState<string | null>(null)
  const [historyTask, setHistoryTask]   = useState<Task | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [showWizard, setShowWizard]     = useState(false)
  const [showMarket, setShowMarket]     = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['tasks', statusFilter],
    queryFn: () => tasksApi.list({ status: statusFilter || undefined, per_page: 100 }),
    refetchInterval: (query) => {
      // 出错时停止轮询，避免持续 401
      if (query.state.errorUpdateCount > 0) return false
      return 15000
    },
  })




  // Fetch full task details when opening edit modal (list API returns TaskListItem with fewer fields)
  const { data: editTaskFull, isFetching: isEditTaskLoading } = useQuery({
    queryKey: ['tasks-edit', editTaskId],
    queryFn: () => tasksApi.get(editTaskId!),
    enabled: !!editTaskId,
  })

  const handleEdit = (task: Task) => {
    setEditTaskId(task.id)
    setShowForm(true)
  }

  const handleCloseForm = () => {
    setShowForm(false)
    setEditTaskId(null)
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
            新建任务
          </button>
        </div>
      </div>

      {/* Status filter tabs */}
      <div role="tablist" aria-label="任务状态筛选" className="flex gap-1 mb-5 border-b border-gray-200">
        {[
          { label: '全部', value: '' },
          { label: '运行中', value: 'active' },
          { label: '已暂停', value: 'paused' },
          { label: '错误', value: 'error' },
        ].map((tab) => (
          <button
            key={tab.value}
            role="tab"
            aria-selected={statusFilter === tab.value}
            onClick={() => setStatusFilter(tab.value)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
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
      {isLoading ? (
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
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50">
          <Spinner className="h-8 w-8" />
        </div>,
        document.body
      )}
      {showForm && (!editTaskId || !isEditTaskLoading) && createPortal(
        <TaskFormModal task={editTaskFull ?? null} onClose={handleCloseForm} />,
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
