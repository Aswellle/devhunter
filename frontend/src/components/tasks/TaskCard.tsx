import { AlertCircle, AlertTriangle, CheckCircle, Pause, Play, Trash2, Zap, Radio } from 'lucide-react'
import { clsx } from 'clsx'
import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import type { Task } from '../../types'
import { tasksApi } from '../../api/tasks'
import { formatDistanceToNow } from '../../utils/time'
import { TaskExecutionStream } from './TaskExecutionStream'

interface TaskCardProps {
  task: Task
  onEdit: (task: Task) => void
  onViewHistory: (task: Task) => void
}

const STATUS_CONFIG = {
  active:  { label: '运行中', badgeClass: 'badge-green',  Icon: CheckCircle },
  paused:  { label: '已暂停', badgeClass: 'badge-gray',   Icon: Pause },
  error:   { label: '错误',   badgeClass: 'badge-red',    Icon: AlertCircle },
}

export function TaskCard({ task, onEdit, onViewHistory }: TaskCardProps) {
  const qc = useQueryClient()
  const { label, badgeClass, Icon } = STATUS_CONFIG[task.status]
  const [showStream, setShowStream] = useState(false)

  const togglePause = useMutation({
    mutationFn: () =>
      tasksApi.update(task.id, {
        status: task.status === 'paused' ? 'active' : 'paused',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success(task.status === 'paused' ? '任务已恢复' : '任务已暂停')
    },
    onError: () => toast.error('操作失败'),
  })

  const deleteTask = useMutation({
    mutationFn: () => tasksApi.delete(task.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('任务已删除（数据保留 30 天）')
    },
    onError: () => toast.error('删除失败'),
  })

  const triggerNow = useMutation({
    mutationFn: () => tasksApi.execute(task.id),
    onSuccess: () => {
      toast.success('已触发立即执行')
      setShowStream(true)
    },
    onError: (e: any) => {
      const msg = e?.response?.data?.error?.message || '触发失败'
      toast.error(msg)
    },
  })

  const handleDelete = () => {
    if (confirm(`确认删除任务「${task.name}」？\n采集结果数据将保留 30 天。`)) {
      deleteTask.mutate()
    }
  }

  const hasConsecWarning = task.consecutive_empty >= 3 && task.status !== 'error'

  return (
    <>
      <div
        className={clsx(
          'card p-4 transition-shadow hover:shadow-md',
          task.status === 'error'  && 'border-red-400 bg-red-50/30',
          hasConsecWarning         && task.status !== 'error' && 'border-yellow-400',
        )}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-semibold text-gray-900 truncate">{task.name}</h3>
              <span className={badgeClass}>
                <Icon className="h-3 w-3 mr-1" />
                {label}
              </span>

              {/* ⚠ 连续空结果警告 */}
              {hasConsecWarning && (
                <span className="badge badge-yellow">
                  <AlertTriangle className="h-3 w-3 mr-1" />
                  连续 {task.consecutive_empty} 次无数据
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500 truncate mt-0.5">{task.source_url}</p>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-0.5 shrink-0">
            {/* 实时流按钮 */}
            <button
              className={clsx(
                'p-1.5 rounded transition-colors',
                showStream
                  ? 'text-green-600 bg-green-50 hover:bg-green-100'
                  : 'text-gray-400 hover:text-green-600 hover:bg-gray-100'
              )}
              onClick={() => setShowStream(true)}
              title="查看实时执行流"
            >
              <Radio className="h-4 w-4" />
            </button>

            {/* 立即执行 */}
            <button
              className="p-1.5 rounded text-gray-400 hover:text-yellow-600 hover:bg-gray-100 transition-colors"
              onClick={() => triggerNow.mutate()}
              disabled={triggerNow.isPending}
              title="立即执行"
            >
              <Zap className="h-4 w-4" />
            </button>

            {/* 暂停/恢复 */}
            <button
              className="p-1.5 rounded text-gray-400 hover:bg-gray-100 transition-colors"
              onClick={() => togglePause.mutate()}
              disabled={togglePause.isPending}
              title={task.status === 'paused' ? '恢复' : '暂停'}
            >
              {task.status === 'paused'
                ? <Play className="h-4 w-4 text-green-600" />
                : <Pause className="h-4 w-4" />}
            </button>

            {/* 删除 */}
            <button
              className="p-1.5 rounded text-gray-300 hover:text-red-500 hover:bg-gray-100 transition-colors"
              onClick={handleDelete}
              title="删除"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
          <span>📅 <b>Cron：</b>{task.cron_expression}</span>
          <span>
            🕐 <b>上次执行：</b>
            {task.last_executed_at ? formatDistanceToNow(task.last_executed_at) : '从未'}
          </span>
          {task.template_id && (
            <span className="badge badge-gray">模板: {task.template_id}</span>
          )}
        </div>

        {/* 错误状态详情 */}
        {task.status === 'error' && (
          <div className="mt-2 flex items-start gap-2 text-xs text-red-600 bg-red-50 rounded px-3 py-2">
            <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            <span>
              连续失败 <b>{task.consecutive_failures}</b> 次，任务已自动暂停。
              请检查数据源和 Selector 配置，修复后手动恢复。
            </span>
          </div>
        )}

        {/* 连续空结果警告 */}
        {hasConsecWarning && task.status !== 'error' && (
          <div className="mt-2 flex items-start gap-2 text-xs text-yellow-700 bg-yellow-50 rounded px-3 py-2">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            <span>
              连续 <b>{task.consecutive_empty}</b> 次采集结果为空，
              Selector 可能已失效，请检查目标页面结构。
            </span>
          </div>
        )}

        {/* Footer */}
        <div className="mt-3 flex items-center gap-2 pt-3 border-t border-gray-100">
          <button className="btn-ghost text-xs py-1" onClick={() => onEdit(task)}>
            编辑配置
          </button>
          <button className="btn-ghost text-xs py-1" onClick={() => onViewHistory(task)}>
            执行历史
          </button>
          <button
            className="btn-ghost text-xs py-1 ml-auto text-green-600 hover:bg-green-50"
            onClick={() => setShowStream(true)}
          >
            <Radio className="h-3 w-3 mr-1" /> 实时流
          </button>
        </div>
      </div>

      {/* ✅ 修复：用 Portal 渲染到 body，避免卡片 DOM 的层叠上下文影响 fixed 定位 */}
      {showStream && createPortal(
        <TaskExecutionStream
          taskId={task.id}
          taskName={task.name}
          onClose={() => setShowStream(false)}
        />,
        document.body
      )}
    </>
  )
}
