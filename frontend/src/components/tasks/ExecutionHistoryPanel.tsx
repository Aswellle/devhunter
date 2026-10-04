/**
 * ExecutionHistoryPanel.tsx
 * 任务执行历史侧边面板
 *
 * 修复：
 * - 移除全屏遮罩（原 fixed inset-0 backdrop）。
 * - 改为纯右侧非阻塞面板，不拦截侧边栏导航和卡片按钮的点击事件。
 * - 添加错误处理和 ARIA 可访问性属性。
 */
import { AlertTriangle, CheckCircle, CircleSlash, Clock, X, XCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { tasksApi } from '../../api/tasks'
import { queryKeys } from '../../api/queryKeys'
import type { Task, TaskExecution } from '../../types'
import { formatDateTime, formatDuration } from '../../utils/time'
import { Spinner } from '../ui/Spinner'

interface ExecutionHistoryPanelProps {
  task: Task
  onClose: () => void
}

// 后端执行状态机含 running（占位）与 interrupted（进程重启恢复），
// 未知状态兜底为 warning，避免解构 undefined 导致面板白屏
const STATUS_ICONS: Record<TaskExecution['status'], { Icon: LucideIcon; cls: string }> = {
  success:     { Icon: CheckCircle,   cls: 'text-success' },
  failure:     { Icon: XCircle,       cls: 'text-danger'   },
  warning:     { Icon: AlertTriangle, cls: 'text-warning'  },
  running:     { Icon: Clock,         cls: 'text-accent'   },
  interrupted: { Icon: CircleSlash,   cls: 'text-muted'    },
}

function ExecRow({ exec }: { exec: TaskExecution }) {
  const { Icon, cls } = STATUS_ICONS[exec.status] ?? STATUS_ICONS.warning
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="flex items-start gap-3 py-3 border-b border-subtle last:border-0">
      <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${cls}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium text-secondary">
            {formatDateTime(exec.executed_at)}
          </span>
          <span className="text-muted">
            {exec.status === 'running' ? '进行中' : formatDuration(exec.duration_ms)}
          </span>
        </div>
        {exec.items_fetched != null && (
          <p className="text-xs text-muted mt-0.5">
            采集 {exec.items_fetched} 条
            {exec.status === 'success' && exec.items_new > 0 ? `，新增 ${exec.items_new} 条` : ''}
          </p>
        )}
        {exec.error_message && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-danger mt-1 text-left hover:underline focus:outline-none focus-visible:underline"
            aria-expanded={expanded}
          >
            {expanded ? '收起' : '查看详情'}
            <pre
              className={`mt-1 text-xs text-danger whitespace-pre-wrap bg-danger-light rounded p-2 font-mono ${
                expanded ? '' : 'line-clamp-3'
              }`}
            >
              {exec.error_message}
            </pre>
          </button>
        )}
      </div>
    </div>
  )
}

export function ExecutionHistoryPanel({ task, onClose }: ExecutionHistoryPanelProps) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: queryKeys.tasks.executions(task.id, { per_page: 50 }),
    queryFn:  () => tasksApi.executions(task.id, { per_page: 50 }),
    // 有执行在进行时 5s 快轮询，空闲时降为 30s（列表按时间倒序，items[0] 即最新）
    refetchInterval: (query) => (query.state.data?.items?.[0]?.status === 'running' ? 5000 : 30000),
  })

  // Escape 关闭面板
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <>
      {/* 透明遮罩：点击关闭面板 */}
      <div
        className="fixed inset-0 md:left-56 z-[49]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-label={`${task.name} 执行历史`}
        className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-md
                    bg-surface shadow-2xl border-l border-subtle flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-subtle shrink-0">
          <div>
            <h2 className="font-bold text-primary text-base">执行历史</h2>
            <p className="text-xs text-muted mt-0.5 truncate max-w-64">{task.name}</p>
          </div>
          <button onClick={onClose} className="btn-ghost p-1" aria-label="关闭">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5">
          {isLoading ? (
            <div className="flex justify-center py-12" role="status" aria-label="加载执行历史中">
              <Spinner />
            </div>
          ) : isError ? (
            <div className="text-center py-12" role="alert">
              <p className="text-sm text-danger mb-2">加载失败</p>
              <button onClick={() => refetch()} className="btn-ghost text-xs py-1">
                重试
              </button>
            </div>
          ) : !data?.items.length ? (
            <div className="text-center py-12 text-muted text-sm" role="status">暂无执行记录</div>
          ) : (
            <>
              <div className="py-3 flex gap-4 text-xs text-muted border-b border-subtle mb-1">
                <span>共 <b>{data.total}</b> 次执行</span>
                <span className="text-success">
                  ✓ {data.items.filter((e) => e.status === 'success').length} 成功
                </span>
                <span className="text-danger">
                  ✗ {data.items.filter((e) => e.status === 'failure').length} 失败
                </span>
                {/* 成功/失败仅统计当前加载的分页，标注范围避免误读为全量比例 */}
                <span className="ml-auto shrink-0">最近 {data.items.length} 条内</span>
              </div>
              {data.items.map((exec) => (
                <ExecRow key={exec.id} exec={exec} />
              ))}
            </>
          )}
        </div>
      </div>
    </>
  )
}
