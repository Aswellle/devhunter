/**
 * TaskExecutionStream.tsx
 * 任务实时执行流面板 —— 双视图：
 *   上半部分：步骤流水线（Pipeline Timeline）
 *   下半部分：原始事件日志 + 新增条目预览
 */
import { Activity, ChevronDown, ChevronUp, ExternalLink, RefreshCw, X } from 'lucide-react'
import { useState } from 'react'
import { clsx } from 'clsx'
import {
  useTaskEventStream,
  type StepState,
  type StepStatus,
  type StreamStatus,
} from '../../hooks/useTaskEventStream'
import { Spinner } from '../ui/Spinner'

interface Props {
  taskId: string
  taskName: string
  onClose: () => void
}

// ─────────────────────────────────────────────────────────
// 步骤图标与颜色
// ─────────────────────────────────────────────────────────
const STEP_ICON: Record<StepStatus, string> = {
  pending: '○',
  active:  '◉',
  done:    '✓',
  skipped: '⊘',
  error:   '✗',
}
const STEP_DOT_CLASS: Record<StepStatus, string> = {
  pending: 'bg-gray-700 border-2 border-gray-600',
  active:  'bg-blue-500 border-2 border-blue-400 animate-pulse',
  done:    'bg-green-500 border-2 border-green-400',
  skipped: 'bg-gray-600 border-2 border-gray-500',
  error:   'bg-red-500 border-2 border-red-400',
}
const STEP_LABEL_CLASS: Record<StepStatus, string> = {
  pending: 'text-gray-300',
  active:  'text-blue-300 font-semibold',
  done:    'text-green-400',
  skipped: 'text-gray-400',
  error:   'text-red-400',
}

// 原始日志事件类型 → 颜色
const LOG_COLOR: Record<string, string> = {
  start:           'text-blue-300',
  step_init:       'text-gray-300',
  fetch_connecting:'text-cyan-400',
  fetch_done:      'text-cyan-300',
  fetch_error:     'text-red-400',
  parse_start:     'text-purple-400',
  parse_done:      'text-purple-300',
  parse_error:     'text-red-400',
  filter_start:    'text-yellow-400',
  filter_done:     'text-yellow-300',
  filter_skip:     'text-gray-400',
  dedup_start:     'text-indigo-400',
  dedup_done:      'text-indigo-300',
  save_start:      'text-green-400',
  save_done:       'text-green-300',
  save_skip:       'text-gray-400',
  success:         'text-green-300 font-semibold',
  failure:         'text-red-400 font-semibold',
  warning:         'text-yellow-400 font-semibold',
  items_preview:   'text-gray-400 text-xs',
  diagnostic:      'text-orange-400',
}
const LOG_ICON: Record<string, string> = {
  start: '🚀', step_init: '⚙',
  fetch_connecting: '🌐', fetch_done: '📄', fetch_error: '🚫',
  parse_start: '🔍', parse_done: '📊', parse_error: '🚫',
  filter_start: '🔎', filter_done: '✅', filter_skip: '⊘',
  dedup_start: '🔄', dedup_done: '🆕',
  save_start: '💾', save_done: '✅', save_skip: '⊘',
  success: '✅', failure: '❌', warning: '⚠️',
  diagnostic: '🔎',
}

// ─────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: StreamStatus }) {
  if (status === 'connecting')
    return <span role="status" aria-live="polite" className="flex items-center gap-1 text-xs text-blue-400"><Spinner className="h-3 w-3" />连接中</span>
  if (status === 'running')
    return (
      <span role="status" aria-live="polite" className="flex items-center gap-1 text-xs text-green-400">
        <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />执行中
      </span>
    )
  if (status === 'done')
    return <span role="status" aria-live="polite" className="text-xs text-gray-400">已完成</span>
  if (status === 'error')
    return <span role="status" aria-live="assertive" className="text-xs text-red-400">连接失败</span>
  if (status === 'waiting')
    return <span role="status" aria-live="polite" className="flex items-center gap-1 text-xs text-yellow-400"><span className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" />等待Worker响应</span>
  return <span role="status" aria-live="polite" className="text-xs text-gray-600">等待任务</span>
}


/** 流水线节点 */
function PipelineNode({ step, isLast }: { step: StepState; isLast: boolean }) {
  return (
    <div className="flex flex-col items-center">
      {/* 节点 + 连线 */}
      <div className="flex items-center w-full">
        <div className={clsx('w-5 h-5 rounded-full shrink-0 flex items-center justify-center text-xs',
          STEP_DOT_CLASS[step.status])}>
          {step.status === 'active' && <span className="text-white text-[9px]">●</span>}
          {step.status === 'done'   && <span className="text-white text-[9px] font-bold">✓</span>}
          {step.status === 'error'  && <span className="text-white text-[9px] font-bold">✗</span>}
          {step.status === 'skipped' && <span className="text-gray-400 text-[9px]">⊘</span>}
        </div>
        {!isLast && (
          <div className={clsx('h-0.5 flex-1 transition-colors',
            step.status === 'done'    ? 'bg-green-500' :
            step.status === 'error'   ? 'bg-red-500' :
            step.status === 'skipped' ? 'bg-gray-600' : 'bg-gray-700'
          )} />
        )}
      </div>
      {/* 标签 */}
      <div className={clsx('text-[10px] mt-1.5 whitespace-nowrap text-center', STEP_LABEL_CLASS[step.status])}>
        {step.label}
      </div>
      {/* 耗时 */}
      {step.durationMs != null && (
        <div className="text-[9px] text-gray-500 mt-0.5">{step.durationMs}ms</div>
      )}
    </div>
  )
}

/** 流水线 + 当前激活步骤详情 */
function PipelinePanel({ steps, isWaiting }: { steps: StepState[]; isWaiting?: boolean }) {
  const activeStep = steps.find((s) => s.status === 'active')
  const lastDone   = [...steps].reverse().find((s) => s.status === 'done' || s.status === 'skipped')

  return (
    <div className="px-4 py-4 border-b border-gray-800">
      {/* 横向流水线 */}
      <div className="flex items-start gap-0">
        {steps.map((step, i) => (
          <PipelineNode key={step.id} step={step} isLast={i === steps.length - 1} />
        ))}
      </div>

      {/* 当前活动步骤详情 */}
      {(activeStep || lastDone) && (
        <div className="mt-3 px-2 py-1.5 rounded bg-gray-800/60 text-xs">
          {activeStep ? (
            <span className="text-blue-300">
              <span className="text-gray-500 mr-1.5">▶</span>
              {activeStep.detail || `${activeStep.label}进行中…`}
            </span>
          ) : lastDone ? (
            <span className={STEP_LABEL_CLASS[lastDone.status]}>
              <span className="text-gray-500 mr-1.5">✓</span>
              {lastDone.detail}
            </span>
          ) : null}
        </div>
      )}

      {/* 等待 Worker 响应指示器 */}
      {isWaiting && !activeStep && (
        <div className="mt-3 px-2 py-1.5 rounded bg-orange-900/30 text-xs text-orange-300 flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse" />
          等待 Worker 响应，任务可能在队列中卡住…
        </div>
      )}
    </div>
  )
}

/** 步骤详情表格 */
function StepsTable({ steps }: { steps: StepState[] }) {
  return (
    <div className="space-y-0.5">
      {steps.map((step) => (
        <div key={step.id}
          className={clsx(
            'flex items-start gap-2 px-3 py-1.5 rounded text-xs',
            step.status === 'active'  && 'bg-blue-900/20',
            step.status === 'error'   && 'bg-red-900/20',
          )}
        >
          <span className={clsx('shrink-0 w-4 text-center font-mono', STEP_LABEL_CLASS[step.status])}>
            {STEP_ICON[step.status]}
          </span>
          <span className={clsx('w-16 shrink-0 font-medium', STEP_LABEL_CLASS[step.status])}>
            {step.label}
          </span>
          <span className={clsx('flex-1 min-w-0', step.status === 'pending' ? 'text-gray-400' : 'text-gray-300')}>
            {step.status === 'pending' ? '等待中' : (step.detail || '—')}
          </span>
          {step.durationMs != null && (
            <span className="text-gray-400 font-mono shrink-0">{step.durationMs}ms</span>
          )}
        </div>
      ))}
    </div>
  )
}

/** 新增条目预览卡片 */
function ItemsPreview({ items, total }: { items: { title: string; url: string; summary?: string }[]; total: number }) {
  if (!items.length) return null
  return (
    <div className="mx-3 mt-2 rounded-lg border border-green-800/50 bg-green-900/10 overflow-hidden">
      <div className="px-3 py-2 border-b border-green-800/40 text-xs text-green-400 font-medium flex items-center gap-1.5">
        <span>📋</span>
        <span>新增条目预览（共 {total} 条，展示前 {items.length} 条）</span>
      </div>
      <div className="divide-y divide-green-900/30">
        {items.map((item, i) => (
          <div key={i} className="px-3 py-2">
            <a
              href={item.url} target="_blank" rel="noopener noreferrer"
              className="flex items-start gap-1 text-xs text-green-300 hover:text-green-200 group"
            >
              <span className="flex-1 line-clamp-2">{item.title}</span>
              <ExternalLink className="h-3 w-3 shrink-0 mt-0.5 opacity-0 group-hover:opacity-100" />
            </a>
            {item.summary && (
              <p className="text-[10px] text-gray-400 mt-0.5 line-clamp-1">{item.summary}</p>
            )}
            <p className="text-[10px] text-gray-500 mt-0.5 font-mono truncate">{item.url}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

/** 原始事件日志行 */
function LogRow({ evt, idx }: { evt: { type: string; message: string; data?: Record<string, unknown>; timestamp?: string }; idx: number }) {
  if (evt.type === 'items_preview') return null   // 单独渲染预览卡片
  const color = LOG_COLOR[evt.type] ?? 'text-gray-400'
  const icon  = LOG_ICON[evt.type]  ?? '▸'

  return (
    <div className={clsx('flex items-start gap-2 py-1 px-2 rounded text-xs font-mono', color)}
      style={{ animationDelay: `${idx * 15}ms` }}>
      <span className="shrink-0 w-4 text-center select-none">{icon}</span>
      <span className="flex-1 min-w-0 break-words">{evt.message}</span>
      {evt.timestamp && (
        <span className="text-gray-500 shrink-0">{evt.timestamp.slice(11, 19)}</span>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────
// 主组件
// ─────────────────────────────────────────────────────────

export function TaskExecutionStream({ taskId, taskName, onClose }: Props) {
  const { events, steps, status, preview, finalData, reset, bottomRef } =
    useTaskEventStream({ taskId, active: true })

  const [showLog, setShowLog] = useState(true)

  const isSuccess = events.some((e) => e.type === 'success')
  const isFailure = events.some((e) => e.type === 'failure')
  const isWarning = events.some((e) => e.type === 'warning')
  const isDone    = status === 'done'
  const isWaiting = status === 'waiting'

  const itemsNew    = (finalData?.items_new  as number) ?? 0
  const itemsFetched = (finalData?.items_fetched as number) ?? 0
  const duration    = (finalData?.duration_ms as number) ?? 0

  return (
    <>
      {/*
       * ✅ 修复根因：添加透明遮罩（z-[49]，低于面板 z-50）
       * - md:left-56 桌面端不覆盖左侧侧边栏，保持导航可用
       * - 点击主内容区任意位置关闭面板（标准抽屉 UX）
       * - 无此遮罩时面板（z-50）静默吞噬主内容区所有点击事件
       */}
      <div
        className="fixed inset-0 md:left-56 z-[49]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${taskName} 实时执行流`}
        className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-lg
                    bg-gray-950 border-l border-gray-800 shadow-2xl flex flex-col"
      >

        {/* ── Header ─────────────────────────────────── */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 bg-gray-900 shrink-0">
          <Activity className="h-4 w-4 text-green-400 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-white truncate">{taskName}</p>
            <p className="text-xs text-gray-500">实时执行流</p>
          </div>
          <StatusBadge status={status} />
          {/* U4/U10: previously only shown when isDone */}
          {(isDone || status === 'error') && (
            <button
              onClick={reset}
              title="重新连接"
              aria-label="重新连接"
              className="p-1 rounded text-gray-500 hover:text-white hover:bg-gray-800 transition-colors"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={onClose}
            aria-label="关闭"
            className="p-1 rounded text-gray-500 hover:text-white hover:bg-gray-800 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ── Pipeline Timeline ──────────────────────── */}
        <PipelinePanel steps={steps} isWaiting={isWaiting} />

        {/* ── 最终结果横幅 ───────────────────────────── */}
        {isDone && (isSuccess || isFailure || isWarning) && (
          <div className={clsx(
            'px-4 py-2.5 flex items-center gap-3 text-sm shrink-0 border-b',
            isSuccess && 'bg-green-900/30 border-green-800/40',
            isFailure && 'bg-red-900/30   border-red-800/40',
            isWarning && 'bg-yellow-900/30 border-yellow-800/40',
          )}>
            <span className="text-base">{isSuccess ? '✅' : isFailure ? '❌' : '⚠️'}</span>
            <div className="flex-1">
              <p className={clsx('font-semibold text-sm',
                isSuccess ? 'text-green-300' : isFailure ? 'text-red-300' : 'text-yellow-300')}>
                {isSuccess ? `执行成功：新增 ${itemsNew} 条` :
                 isFailure ? '执行失败' : '完成但无新增数据'}
              </p>
              {isSuccess && (
                <p className="text-xs text-gray-400 mt-0.5">
                  抓取 {itemsFetched} 条 · 耗时 {duration}ms
                </p>
              )}
            </div>
          </div>
        )}

        {/* ── 滚动区域 ───────────────────────────────── */}
        <div className="flex-1 overflow-y-auto min-h-0">

          {/* 步骤详情表格 */}
          <div className="px-1 py-3">
            <StepsTable steps={steps} />
          </div>

          {/* 新增条目预览 */}
          {preview.length > 0 && (
            <ItemsPreview items={preview} total={itemsNew || preview.length} />
          )}

          {/* 分隔 + 日志折叠 */}
          <div className="px-3 pt-3">
            <button
              onClick={() => setShowLog((v) => !v)}
              className="w-full flex items-center gap-2 text-xs text-gray-600
                         hover:text-gray-400 transition-colors py-1"
            >
              <span className="flex-1 border-t border-gray-800" />
              <span className="shrink-0 flex items-center gap-1">
                原始日志 ({events.filter((e) => e.type !== 'items_preview').length} 条)
                {showLog ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              </span>
              <span className="flex-1 border-t border-gray-800" />
            </button>
          </div>

          {/* 原始日志 */}
          {showLog && (
            <div className="px-1 pb-3 space-y-0">
              {status === 'connecting' && (
                <div className="flex items-center gap-2 px-3 py-4 text-blue-400 text-xs">
                  <Spinner className="h-3.5 w-3.5" /> 正在连接事件流…
                </div>
              )}
              {status === 'idle' && (
                <p className="px-3 py-4 text-xs text-gray-700">
                  等待任务执行，点击「立即执行」或等待定时触发…
                </p>
              )}
              {events
                .filter((e) => e.type !== 'items_preview')
                .map((evt, i) => (
                  <LogRow key={i} evt={evt} idx={i} />
                ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* ── Footer ─────────────────────────────────── */}
        <div className="px-4 py-2 border-t border-gray-800 bg-gray-900
                        text-xs text-gray-400 flex items-center justify-between shrink-0">
          <span>{events.length} 条事件</span>
          {status === 'running' && (
            <span className="text-green-500 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              实时更新中
            </span>
          )}
          {isDone && (
            <span className="text-gray-400">
              {isSuccess ? `新增 ${itemsNew} 条` : isFailure ? '执行失败' : '无新增数据'}
            </span>
          )}
        </div>
      </div>
    </>
  )
}
