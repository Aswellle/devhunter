/**
 * ExecutionHistoryPanel.tsx
 * 任务执行历史侧边面板
 *
 * ✅ 修复：移除全屏遮罩（原 fixed inset-0 backdrop）。
 * 改为纯右侧非阻塞面板，不拦截侧边栏导航和卡片按钮的点击事件。
 */
import { AlertTriangle, CheckCircle, X, XCircle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { tasksApi } from '../../api/tasks'
import type { Task, TaskExecution } from '../../types'
import { formatDateTime, formatDuration } from '../../utils/time'
import { Spinner } from '../ui/Spinner'

interface ExecutionHistoryPanelProps {
  task: Task
  onClose: () => void
}

const STATUS_ICONS = {
  success: { Icon: CheckCircle,   cls: 'text-green-500' },
  failure: { Icon: XCircle,       cls: 'text-red-500'   },
  warning: { Icon: AlertTriangle, cls: 'text-yellow-500' },
}

function ExecRow({ exec }: { exec: TaskExecution }) {
  const { Icon, cls } = STATUS_ICONS[exec.status]
  // U11: `truncate` cut the error message to a single line — exactly the
  // moment a user most needs the full text to diagnose a failure. Clamp to
  // 3 lines by default with a toggle to expand the rest instead of hiding it.
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="flex items-start gap-3 py-3 border-b border-gray-100 last:border-0">
      <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${cls}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm text-gray-700">
            抓取 <b>{exec.items_fetched}</b> 条，新增{' '}
            <b className="text-primary-600">{exec.items_new}</b> 条
          </span>
          <span className="text-xs text-gray-400 shrink-0">
            {formatDuration(exec.duration_ms)}
          </span>
        </div>
        <div className="text-xs text-gray-400 mt-0.5">
          {formatDateTime(exec.executed_at)}
        </div>
        {exec.error_message && (
          <div className="mt-1 bg-red-50 rounded px-2 py-1">
            <p className={`text-xs text-red-500 whitespace-pre-wrap ${expanded ? '' : 'line-clamp-3'}`}>
              {exec.error_message}
            </p>
            {exec.error_message.length > 120 && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="text-xs text-red-400 hover:text-red-600 underline mt-0.5"
              >
                {expanded ? '收起' : '展开全部'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export function ExecutionHistoryPanel({ task, onClose }: ExecutionHistoryPanelProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['executions', task.id],
    queryFn:  () => tasksApi.executions(task.id, { per_page: 50 }),
    refetchInterval: 10000,
  })

  /**
   * ✅ 修复核心：
   *   - 去掉 fixed inset-0 外层容器（全屏遮罩是问题根源）
   *   - 改为 fixed right-0 top-0 bottom-0：只占右侧，左侧内容可自由交互
   *   - 去掉 absolute inset-0 backdrop：不再拦截侧边栏和按钮的点击事件
   */
  return (
    <>
      {/*
       * ✅ 修复根因：添加透明遮罩（z-[49]，低于面板 z-50）
       * - 覆盖主内容区，点击即可关闭面板（标准抽屉 UX）
       * - md:left-56 在桌面端不覆盖左侧侧边栏（w-56=224px），侧边栏导航保持可用
       * - 移动端 left-0 全屏覆盖，防止面板背后的内容被意外点击
       * 无此遮罩时，面板（z-50）会静默吞噬主内容区的所有点击事件（包括「编辑配置」按钮）
       */}
      <div
        className="fixed inset-0 md:left-56 z-[49]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-md
                      bg-white shadow-2xl border-l border-gray-200 flex flex-col">

      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
        <div>
          <h2 className="font-bold text-gray-900 text-base">执行历史</h2>
          <p className="text-xs text-gray-500 mt-0.5 truncate max-w-64">{task.name}</p>
        </div>
        <button onClick={onClose} className="btn-ghost p-1" title="关闭" aria-label="关闭">
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-5">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Spinner />
          </div>
        ) : !data?.items.length ? (
          <div className="text-center py-12 text-gray-400 text-sm">暂无执行记录</div>
        ) : (
          <>
            <div className="py-3 flex gap-4 text-xs text-gray-500 border-b border-gray-100 mb-1">
              <span>共 <b>{data.total}</b> 次执行</span>
              <span className="text-green-600">
                ✓ {data.items.filter((e) => e.status === 'success').length} 成功
              </span>
              <span className="text-red-500">
                ✗ {data.items.filter((e) => e.status === 'failure').length} 失败
              </span>
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
