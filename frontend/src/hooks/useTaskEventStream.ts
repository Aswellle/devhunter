import { useCallback, useEffect, useRef, useState } from 'react'

export type StreamStatus = 'idle' | 'connecting' | 'running' | 'done' | 'error' | 'waiting'

// ── 步骤定义 ─────────────────────────────────────────────
export type StepId = 'init' | 'fetch' | 'parse' | 'filter' | 'dedup' | 'save'
export type StepStatus = 'pending' | 'active' | 'done' | 'skipped' | 'error'

export interface StepState {
  id: StepId
  label: string
  status: StepStatus
  detail: string
  startedAt: number | null   // performance.now()
  durationMs: number | null
}

// ── 原始事件 ─────────────────────────────────────────────
export interface StreamEvent {
  type: string
  message: string
  data?: Record<string, unknown>
  timestamp?: string
}

// ── 条目预览 ─────────────────────────────────────────────
export interface ItemPreview {
  title: string
  url: string
  summary?: string
}

// ── 事件类型 → 步骤映射 ─────────────────────────────────
const EVENT_TO_STEP: Record<string, { step: StepId; activate?: boolean; done?: boolean; skip?: boolean; error?: boolean }> = {
  step_init:       { step: 'init',   done: true  },
  fetch_connecting:{ step: 'fetch',  activate: true },
  fetch_done:      { step: 'fetch',  done: true  },
  fetch_error:     { step: 'fetch',  error: true },
  parse_start:     { step: 'parse',  activate: true },
  parse_done:      { step: 'parse',  done: true  },
  parse_error:     { step: 'parse',  error: true },
  filter_start:    { step: 'filter', activate: true },
  filter_done:     { step: 'filter', done: true  },
  filter_skip:     { step: 'filter', skip: true  },
  dedup_start:     { step: 'dedup',  activate: true },
  dedup_done:      { step: 'dedup',  done: true  },
  save_start:      { step: 'save',   activate: true },
  save_done:       { step: 'save',   done: true  },
  save_skip:       { step: 'save',   skip: true  },
}

const INITIAL_STEPS: StepState[] = [
  { id: 'init',   label: '初始化', status: 'pending', detail: '',  startedAt: null, durationMs: null },
  { id: 'fetch',  label: '页面抓取', status: 'pending', detail: '', startedAt: null, durationMs: null },
  { id: 'parse',  label: 'HTML 解析', status: 'pending', detail: '', startedAt: null, durationMs: null },
  { id: 'filter', label: '关键词过滤', status: 'pending', detail: '', startedAt: null, durationMs: null },
  { id: 'dedup',  label: '去重检查', status: 'pending', detail: '', startedAt: null, durationMs: null },
  { id: 'save',   label: '写入数据库', status: 'pending', detail: '', startedAt: null, durationMs: null },
]

function cloneSteps(steps: StepState[]): StepState[] {
  return steps.map((s) => ({ ...s }))
}

// ── Hook ─────────────────────────────────────────────────
export function useTaskEventStream({ taskId, active }: { taskId: string | null; active: boolean }) {
  const [events, setEvents]         = useState<StreamEvent[]>([])
  const [steps, setSteps]           = useState<StepState[]>(cloneSteps(INITIAL_STEPS))
  const [status, setStatus]         = useState<StreamStatus>('idle')
  const [preview, setPreview]       = useState<ItemPreview[]>([])
  const [finalData, setFinalData]   = useState<Record<string, unknown> | null>(null)

  const abortRef   = useRef<AbortController | null>(null)
  const bottomRef  = useRef<HTMLDivElement | null>(null)
  const stepsRef   = useRef<StepState[]>(cloneSteps(INITIAL_STEPS))
  const retryCount = useRef(0)
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const reset = useCallback(() => {
    abortRef.current?.abort()
    if (retryTimer.current) clearTimeout(retryTimer.current)
    const fresh = cloneSteps(INITIAL_STEPS)
    stepsRef.current = fresh
    setSteps(fresh)
    setEvents([])
    setPreview([])
    setFinalData(null)
    setStatus('idle')
    retryCount.current = 0
  }, [])

  // 根据事件更新步骤状态机
  const applyEvent = useCallback((evt: StreamEvent) => {
    const mapping = EVENT_TO_STEP[evt.type]
    if (!mapping) return

    const now    = performance.now()
    const next   = cloneSteps(stepsRef.current)
    const target = next.find((s) => s.id === mapping.step)
    if (!target) return

    if (mapping.activate && target.status === 'pending') {
      target.status    = 'active'
      target.startedAt = now
      target.detail    = evt.message
    } else if (mapping.done) {
      if (target.status === 'active' && target.startedAt != null) {
        target.durationMs = Math.round(now - target.startedAt)
      }
      target.status = 'done'
      target.detail = evt.message
    } else if (mapping.skip) {
      target.status = 'skipped'
      target.detail = evt.message
    } else if (mapping.error) {
      target.status = 'error'
      target.detail = evt.message
    }

    stepsRef.current = next
    setSteps(next)
  }, [])

  useEffect(() => {
    if (!taskId || !active) return

    abortRef.current?.abort()
    if (retryTimer.current) clearTimeout(retryTimer.current)
    const controller = new AbortController()
    abortRef.current = controller

    const fresh = cloneSteps(INITIAL_STEPS)
    stepsRef.current = fresh
    setSteps(fresh)
    setEvents([])
    setPreview([])
    setFinalData(null)
    setStatus('waiting')
    retryCount.current = 0

    // Token 通过 httpOnly Cookie 自动发送，无需手动携带

    // Stuck timer: fires 25s after transition to 'waiting' if no real event arrived
    const stuckTimerId = setTimeout(() => {
      setEvents((prev) => [...prev, {
        type: 'warning',
        message: '⚠️ 超过 20 秒无活动，执行可能卡住。请检查任务状态是否为 active，或重启服务。',
      }])
    }, 25_000)

    ;(async () => {
      const MAX_RETRIES = 3
      const RETRY_DELAY = 2000

      // eslint-disable-next-line no-constant-condition
      while (true) {
        try {
          const res = await fetch(`/api/tasks/${taskId}/events`, {
            credentials: 'include',
            signal: controller.signal,
          })

          if (!res.ok || !res.body) {
            clearTimeout(stuckTimerId)
            setStatus('error')
            return
          }

          // Real event arrived → worker is alive, switch to running
          clearTimeout(stuckTimerId)
          setStatus('running')
          retryCount.current = 0

          const reader  = res.body.getReader()
          const decoder = new TextDecoder()
          let   buffer  = ''

          // eslint-disable-next-line no-constant-condition
          while (true) {
            const { done, value } = await reader.read()
            if (done) break

            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() ?? ''

            for (const line of lines) {
              if (!line.startsWith('data: ')) continue
              try {
                const evt: StreamEvent = JSON.parse(line.slice(6))

                // 步骤状态机
                applyEvent(evt)

                // 条目预览
                if (evt.type === 'items_preview' && Array.isArray(evt.data?.items)) {
                  setPreview(evt.data.items as ItemPreview[])
                }

                // 最终事件
                if (['success', 'failure', 'warning'].includes(evt.type)) {
                  setFinalData(evt.data ?? null)
                  setStatus('done')
                  clearTimeout(stuckTimerId)
                  return
                }

                // Add to log
                if (evt.type !== 'connected') {
                  setEvents((prev) => [...prev, evt])
                }

                // Handle diagnostic events
                if (evt.type === 'diagnostic') {
                  const hint = (evt.data as any)?.hint
                  if (hint === 'worker_not_started') {
                    setEvents((prev) => [...prev, {
                      type: 'warning',
                      message: '⚠️ Worker 尚未响应，任务可能卡在队列中，或 APScheduler 未正确加载该任务。请检查任务状态是否为 active。',
                    }])
                  }
                }

              } catch { /* ignore parse error */ }
            }
          }

          // Stream ended without terminal event → attempt retry
          setStatus((s) => s === 'running' ? 'waiting' : s)
          break

        } catch (err: unknown) {
          if ((err as Error).name === 'AbortError') {
            clearTimeout(stuckTimerId)
            return
          }
          // Non-abort error: attempt retry
          if (retryCount.current < MAX_RETRIES) {
            retryCount.current++
            setStatus('connecting')
            setEvents((prev) => [...prev, {
              type: 'warning',
              message: `⚠️ 连接中断，${RETRY_DELAY / 1000}s 后自动重试 (${retryCount.current}/${MAX_RETRIES})`,
            }])
            await new Promise((r) => { retryTimer.current = setTimeout(r, RETRY_DELAY) })
          } else {
            clearTimeout(stuckTimerId)
            setStatus('error')
            setEvents((prev) => [...prev, {
              type: 'warning',
              message: `⚠️ 连接失败，已重试 ${MAX_RETRIES} 次。请手动刷新页面重试。`,
            }])
            return
          }
        }
      }
    })()

    return () => controller.abort()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId, active])

  // 自动滚动
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  return { events, steps, status, preview, finalData, reset, bottomRef }
}
