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
  startedAt: number | null
  durationMs: number | null
}

// ── 原始事件 ─────────────────────────────────────────────
export interface StreamEvent {
  id: string
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
  { id: 'init',  label: '加载配置',  status: 'pending', detail: '', startedAt: null, durationMs: null },
  { id: 'fetch', label: '网络抓取',  status: 'pending', detail: '', startedAt: null, durationMs: null },
  { id: 'parse', label: '解析内容',  status: 'pending', detail: '', startedAt: null, durationMs: null },
  { id: 'filter',label: '关键词过滤',status: 'pending', detail: '', startedAt: null, durationMs: null },
  { id: 'dedup', label: '去重',      status: 'pending', detail: '', startedAt: null, durationMs: null },
  { id: 'save',  label: '写入数据库',status: 'pending', detail: '', startedAt: null, durationMs: null },
]

function cloneSteps(steps: StepState[]): StepState[] {
  return steps.map((s) => ({ ...s }))
}

// E2: 指数退避 — 1s → 2s → 4s → 8s → 16s → 30s max
function backoffDelay(attempt: number): number {
  return Math.min(1000 * Math.pow(2, attempt), 30_000)
}

// E1: 安全提取 hint 字段（避免 any）
function extractHint(data: Record<string, unknown> | undefined): string | undefined {
  if (data && typeof data === "object" && "hint" in data) {
    const hint = data.hint
    return typeof hint === "string" ? hint : undefined
  }
  return undefined
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
  const lastEventIdRef = useRef<string>("")

  const reset = useCallback(() => {
    abortRef.current?.abort()
    clearTimeout(retryTimer.current ?? undefined)
    const fresh = cloneSteps(INITIAL_STEPS)
    stepsRef.current = fresh
    setSteps(fresh)
    setEvents([])
    setPreview([])
    setFinalData(null)
    setStatus('idle')
    retryCount.current = 0
    lastEventIdRef.current = ""
  }, [])

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
    clearTimeout(retryTimer.current ?? undefined)
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
    lastEventIdRef.current = ""

    const stuckTimerId = setTimeout(() => {
      if (controller.signal.aborted) return
      setEvents((prev) => [...prev, {
        id: 'stuck-warning',
        type: 'warning',
        message: '⚠️ 超过 20 秒无活动，执行可能卡住。请检查任务状态是否为 active，或重启服务。',
      }])
    }, 25_000)

    ;(async () => {
      const MAX_RETRIES = 5

      while (true) {
        if (controller.signal.aborted) break

        try {
          const headers: Record<string, string> = {}
          if (lastEventIdRef.current) {
            headers["Last-Event-ID"] = lastEventIdRef.current
          }

          const res = await fetch(`/api/tasks/${taskId}/events`, {
            credentials: 'include',
            signal: controller.signal,
            headers,
          })

          if (!res.ok || !res.body) {
            clearTimeout(stuckTimerId)
            setStatus('error')
            return
          }

          clearTimeout(stuckTimerId)
          setStatus('running')
          retryCount.current = 0

          const reader  = res.body.getReader()
          const decoder = new TextDecoder()
          let   buffer  = ''

          while (true) {
            const { done, value: chunk } = await reader.read()
            if (done) {
              // 处理缓冲区中剩余的不完整数据
              if (buffer.trim().startsWith('data: ')) {
                try {
                  const evt: StreamEvent = JSON.parse(buffer.trim().slice(6))
                  applyEvent(evt)
                  if (evt.type !== 'connected') {
                    setEvents((prev) => {
                      const MAX_EVENTS = 500
                      const next = [...prev, evt]
                      return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next
                    })
                  }
                } catch { /* ignore parse error */ }
              }
              clearTimeout(stuckTimerId)
              break
            }

            buffer += decoder.decode(chunk, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() ?? ''


            for (const line of lines) {
              if (!line.startsWith('data: ')) continue
              try {
                const evt: StreamEvent = JSON.parse(line.slice(6))

                if (evt.id && evt.id !== 'connected' && evt.id !== 'timeout') {
                  lastEventIdRef.current = evt.id
                }

                applyEvent(evt)

                if (evt.type === 'items_preview' && Array.isArray(evt.data?.items)) {
                  setPreview(evt.data.items as ItemPreview[])
                }

                if (['success', 'failure', 'warning'].includes(evt.type)) {
                  setFinalData(evt.data ?? null)
                  setStatus('done')
                  clearTimeout(stuckTimerId)
                  return
                }

                if (evt.type !== 'connected') {
                  setEvents((prev) => {
                    const MAX_EVENTS = 500
                    const next = [...prev, evt]
                    return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next
                  })
                }

                if (evt.type === 'diagnostic') {
                  const hint = extractHint(evt.data)
                  if (hint === 'worker_not_started') {
                    setEvents((prev) => {
                      const MAX_EVENTS = 500
                      const next = [...prev, {
                        id: 'diagnostic-warn',
                        type: 'warning',
                        message: '⚠️ Worker 尚未响应，任务可能卡在队列中，或 APScheduler 未正确加载该任务。请检查任务状态是否为 active。',
                      }]
                      return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next
                    })
                  }
                }

              } catch { /* ignore parse error */ }
            }
          }

          setStatus((s) => s === 'running' ? 'waiting' : s)
          break

        } catch (err: unknown) {
          if ((err as Error).name === 'AbortError') {
            clearTimeout(stuckTimerId)
            return
          }
          if (retryCount.current < MAX_RETRIES && !controller.signal.aborted) {
            retryCount.current++
            const delay = backoffDelay(retryCount.current - 1)
            setStatus('connecting')
            setEvents((prev) => [...prev, {
              id: `retry-${retryCount.current}`,
              type: 'warning',
              message: `⚠️ 连接中断，${(delay / 1000).toFixed(0)}s 后自动重试 (${retryCount.current}/${MAX_RETRIES})`,
            }])
            let retryResolve: () => void
            const promise = new Promise<void>((r) => { retryResolve = r })
            retryTimer.current = setTimeout(() => retryResolve(), delay)

            await promise
          } else {
            clearTimeout(stuckTimerId)
            setStatus('error')
            setEvents((prev) => {
              const MAX_EVENTS = 500
              const next = [...prev, {
                id: 'final-error',
                type: 'warning',
                message: `⚠️ 连接失败，已重试 ${MAX_RETRIES} 次。请手动刷新页面重试。`,
              }]
              return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next
            })
            return
          }
        }
      }
    })()

    return () => {
      controller.abort()
      clearTimeout(stuckTimerId)
      clearTimeout(retryTimer.current ?? undefined)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId, active])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  return { events, steps, status, preview, finalData, reset, bottomRef }
}
