import { AlertCircle, AlertTriangle, CheckCircle, Pause, Play, Trash2, Zap, Radio } from 'lucide-react'
import { clsx } from 'clsx'
import { useState, useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import type { Task } from '../../types'
import { tasksApi } from '../../api/tasks'
import { errorMessage } from '../../api/client'
import { formatDistanceToNow } from '../../utils/time'
import { describeCron } from '../../utils/schedule'
import { Badge } from '../ui/Badge'
import { TaskExecutionStream } from './TaskExecutionStream'

interface TaskCardProps {
  task: Task
  onEdit: (task: Task) => void
  onViewHistory: (task: Task) => void
}

// 连续空结果次数阈值：超过此值显示警告
const CONSECUTIVE_EMPTY_WARNING_THRESHOLD = 3

type BadgeColor = 'green' | 'red' | 'yellow' | 'primary' | 'gray'

const STATUS_CONFIG: Record<string, { label: string; color: BadgeColor; Icon: typeof CheckCircle }> = {
  active:  { label: '运行中', color: 'green', Icon: CheckCircle },
  paused:  { label: '已暂停', color: 'gray',  Icon: Pause },
  error:   { label: '错误',   color: 'red',   Icon: AlertCircle },
  draft:   { label: '草稿',   color: 'gray',  Icon: Pause },
}

/**
 * 统一尺寸的图标按钮：四个操作的点击区与图标严格对齐，
 * 不会因为某个按钮的 hover 背景/描述文字长短而抖动。
 */
function IconAction({
  label, title, onClick, disabled, tone = 'default', children,
}: {
  label: string
  title: string
  onClick: () => void
  disabled?: boolean
  tone?: 'default' | 'green' | 'danger' | 'muted'
  children: ReactNode
}) {
  const toneClass = {
    default: 'text-gray-400 hover:text-yellow-600 hover:bg-gray-100',
    green:   'text-gray-400 hover:text-green-600 hover:bg-gray-100',
    danger:  'text-gray-300 hover:text-red-500 hover:bg-gray-100',
    muted:   'text-gray-300 cursor-not-allowed',
  }[tone]

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={label}
      className={clsx(
        'inline-flex h-8 w-8 items-center justify-center rounded transition-colors',
        toneClass,
        disabled && tone !== 'muted' && 'opacity-50 cursor-not-allowed',
      )}
    >
      {children}
    </button>
  )
}

export function TaskCard({ task, onEdit, onViewHistory }: TaskCardProps) {
  const qc = useQueryClient()
  const status = STATUS_CONFIG[task.status] ?? STATUS_CONFIG.draft
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
    onError: (e: unknown) => {
      // 拦截器产出的是 ApiError（无 .response），统一用 errorMessage 提取
      toast.error(errorMessage(e, '触发失败'))
    },
  })

  // U9: replaces window.confirm() — blocking native dialog, no visual
  // consistency with the app, and untestable. Two-step inline confirm
  // mirrors the pattern used in ItemsPage's batch-delete button.
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  // U9: 4s inactivity timer disarms the confirm so a half-finished action
  // can't linger (onBlur alone won't fire if the user switches tabs).
  useEffect(() => {
    if (!confirmingDelete) return
    const id = setTimeout(() => setConfirmingDelete(false), 4000)
    return () => clearTimeout(id)
  }, [confirmingDelete])

  const handleDeleteClick = () => {
    if (!confirmingDelete) {
      setConfirmingDelete(true)
      return
    }
    setConfirmingDelete(false)
    deleteTask.mutate()
  }

  const hasConsecWarning = task.consecutive_empty >= CONSECUTIVE_EMPTY_WARNING_THRESHOLD && task.status !== 'error'
  const keywords = task.keywords ?? []
  const keywordsText = keywords.length
    ? keywords.slice(0, 3).join('、') + (keywords.length > 3 ? ` 等 ${keywords.length} 个` : '')
    : '全量采集'
  const scheduleText = describeCron(task.cron_expression)

  return (
    <>
      <div
        className={clsx(
          'card p-4 transition-shadow hover:shadow-md flex flex-col gap-3',
          task.status === 'error'  && 'border-red-400 bg-red-50/30',
          hasConsecWarning         && task.status !== 'error' && 'border-yellow-400',
        )}
      >
        {/* ── 标题行：标题截断，状态徽章永不换行 ── */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 min-w-0">
              <h3 className="font-semibold text-gray-900 truncate" title={task.name}>
                {task.name}
              </h3>
              <Badge color={status.color} className="shrink-0">
                <status.Icon className="h-3 w-3 mr-1" />
                {status.label}
              </Badge>
              {hasConsecWarning && (
                <Badge color="yellow" className="shrink-0">
                  <AlertTriangle className="h-3 w-3 mr-1" />
                  连续 {task.consecutive_empty} 次无数据
                </Badge>
              )}
            </div>
            {/* 长 URL 截断并保留完整值在 tooltip 里，不撑破卡片 */}
            <p className="text-xs text-gray-500 truncate mt-1" title={task.source_url}>
              {task.source_url}
            </p>
          </div>

          {/* ── 操作区：固定尺寸，不随内容伸缩 ── */}
          <div className="flex items-center gap-0.5 shrink-0 -mr-1">
            <IconAction
              label="查看实时执行流"
              title="查看实时执行流"
              tone="green"
              onClick={() => setShowStream(true)}
            >
              <Radio className={clsx('h-4 w-4', showStream && 'text-green-600')} />
            </IconAction>

            <IconAction
              label={task.status === 'paused' ? '任务已暂停，无法立即执行' : '立即执行'}
              title={task.status === 'paused' ? '任务已暂停，请先恢复' : '立即执行'}
              onClick={() => triggerNow.mutate()}
              disabled={triggerNow.isPending || task.status === 'paused'}
              tone={task.status === 'paused' ? 'muted' : 'default'}
            >
              <Zap className="h-4 w-4" />
            </IconAction>

            <IconAction
              label={task.status === 'paused' ? '恢复任务' : '暂停任务'}
              title={task.status === 'paused' ? '恢复' : '暂停'}
              onClick={() => togglePause.mutate()}
              disabled={togglePause.isPending}
              tone="default"
            >
              {task.status === 'paused'
                ? <Play className="h-4 w-4 text-green-600" />
                : <Pause className="h-4 w-4" />}
            </IconAction>

            <button
              type="button"
              onClick={handleDeleteClick}
              onBlur={() => setConfirmingDelete(false)}
              title={confirmingDelete ? '再次点击确认删除' : '删除'}
              aria-label={confirmingDelete ? '再次点击确认删除任务' : '删除任务'}
              className={clsx(
                'inline-flex h-8 w-8 items-center justify-center rounded transition-colors',
                confirmingDelete
                  ? 'bg-red-600 text-white hover:bg-red-500'
                  : 'text-gray-300 hover:text-red-500 hover:bg-gray-100',
              )}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* ── 元信息：两列网格，值一律截断，卡片之间对齐 ── */}
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 text-xs text-gray-500">
          <div className="flex items-center gap-1.5 min-w-0">
            <dt className="shrink-0 text-gray-400">调度</dt>
            <dd className="truncate font-medium text-gray-600" title={`Cron: ${task.cron_expression}`}>
              {scheduleText}
            </dd>
          </div>
          <div className="flex items-center gap-1.5 min-w-0">
            <dt className="shrink-0 text-gray-400">上次执行</dt>
            <dd className="truncate font-medium text-gray-600">
              {task.last_executed_at ? formatDistanceToNow(task.last_executed_at) : '从未执行'}
            </dd>
          </div>
          <div className="flex items-center gap-1.5 min-w-0">
            <dt className="shrink-0 text-gray-400">模板</dt>
            <dd className="truncate font-medium text-gray-600" title={task.template_id ?? '自定义'}>
              {task.template_id ?? '自定义配置'}
            </dd>
          </div>
          <div className="flex items-center gap-1.5 min-w-0">
            <dt className="shrink-0 text-gray-400">关键词</dt>
            <dd
              className={clsx('truncate font-medium', keywords.length ? 'text-gray-600' : 'text-gray-400')}
              title={keywords.length ? keywords.join('、') : '未设置关键词：全量采集'}
            >
              {keywordsText}
            </dd>
          </div>
        </dl>

        {/* ── 异常提示 ── */}
        {task.status === 'error' && (
          <div className="flex items-start gap-2 text-xs text-red-600 bg-red-50 rounded px-3 py-2">
            <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            <span>
              连续失败 <b>{task.consecutive_failures}</b> 次，任务已自动暂停。
              请检查数据源和 Selector 配置，修复后手动恢复。
            </span>
          </div>
        )}

        {hasConsecWarning && task.status !== 'error' && (
          <div className="flex items-start gap-2 text-xs text-yellow-700 bg-yellow-50 rounded px-3 py-2">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            <span>
              连续 <b>{task.consecutive_empty}</b> 次采集结果为空，
              Selector 可能已失效，请检查目标页面结构。
            </span>
          </div>
        )}

        {/* ── 底部操作 ── */}
        <div className="flex items-center gap-2 pt-3 border-t border-gray-100 mt-auto">
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
        document.body,
      )}
    </>
  )
}
