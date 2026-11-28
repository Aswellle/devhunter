/**
 * useDwellTracking：卡片停留埋点（工作流 D：行为埋点质量）。
 *
 * 语义（02 闭环 D）：
 * - 只有在「前台可见」时计时——IntersectionObserver ≥60% 可见且
 *   document.visibilityState === 'visible' 才累计；
 * - 最小停留阈值 MIN_DWELL_MS（默认 5s）：不足即放弃，不把"划过"
 *   当成深度阅读；
 * - 每条目每个浏览器会话最多上报一次（sessionStorage 去重），
 *   服务端另有 60 分钟去重窗口兜底（工作流 D 行为埋点质量）。
 */
import { useEffect, useRef } from 'react'
import { userPrefsApi } from '../api/user_prefs'

export const MIN_DWELL_MS = 5_000

const DWELL_VISIBILITY_RATIO = 0.6

function alreadySent(item_id: string): boolean {
  try {
    return sessionStorage.getItem(`dwell-sent-${item_id}`) === '1'
  } catch {
    return false
  }
}

function markSent(item_id: string): void {
  try {
    sessionStorage.setItem(`dwell-sent-${item_id}`, '1')
  } catch {
    // 隐私模式等 sessionStorage 不可用：静默放弃持久化去重
  }
}

export function useDwellTracking(item_id: string | undefined): void {
  // ref 持有计时器与起止时间，避免 visibility 回调频繁重建 observer
  const timerRef = useRef<number | null>(null)
  const startedAtRef = useRef<number | null>(null)

  useEffect(() => {
    if (!item_id || alreadySent(item_id)) return

    const stopTimer = () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
      startedAtRef.current = null
    }

    const sendDwell = () => {
      const startedAt = startedAtRef.current
      stopTimer()
      if (startedAt === null || alreadySent(item_id)) return
      const dwellMs = Date.now() - startedAt
      if (dwellMs < MIN_DWELL_MS) return
      markSent(item_id)
      // fire-and-forget：埋点失败不影响阅读
      userPrefsApi
        .recordInteraction({
          item_id,
          interaction_type: 'dwell',
          dwell_seconds: Math.round(dwellMs / 1000),
        })
        .catch(() => {})
    }

    const startTimer = () => {
      if (timerRef.current !== null || startedAtRef.current !== null) return
      startedAtRef.current = Date.now()
      timerRef.current = window.setTimeout(
        () => sendDwell(),
        MIN_DWELL_MS,
      )
    }

    const isForeground = () =>
      document.visibilityState === 'visible' && !document.hidden

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (
            entry.intersectionRatio >= DWELL_VISIBILITY_RATIO &&
            isForeground()
          ) {
            startTimer()
          } else {
            // 离开视口/切后台：重置计时（不足阈值则丢弃）
            sendDwell()
          }
        }
      },
      { threshold: [0, DWELL_VISIBILITY_RATIO, 1] },
    )

    const onVisibilityChange = () => {
      if (isForeground()) {
        // 回到前台且仍可见时由 observer 重新触发；这里只处理隐藏
      }
      if (!isForeground()) {
        sendDwell()
      }
    }

    const el = document.getElementById(`item-card-${item_id}`)
    if (el) {
      observer.observe(el)
    }
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      observer.disconnect()
      document.removeEventListener('visibilitychange', onVisibilityChange)
      stopTimer()
    }
  }, [item_id])
}
