/**
 * PullToRefresh.tsx
 * 移动端下拉刷新（借鉴 AIHOT 移动壳层的 PullToRefresh）。
 *
 * - 仅触屏设备启用（pointer: coarse / hover: none / maxTouchPoints>0），
 *   桌面端原样渲染 children，零开销
 * - 手势：滚动容器处于顶部时继续下拉 → 指示器随拉动位移（0.5 阻尼）→
 *   越过阈值松手触发 onRefresh → 完成后指示器收回
 * - 不调用 preventDefault：滚动容器以 overscroll-y-contain 抑制浏览器
 *   原生下拉刷新（见 AppLayout 的 main），触摸监听全部 passive，
 *   不阻塞正常滚动
 * - 滚动容器约定为布局的 #main-content（与跳转链接共用的稳定锚点）
 */
import { useEffect, useRef, useState } from 'react'
import { ArrowDown, Loader2 } from 'lucide-react'
import { clsx } from 'clsx'

const INDICATOR_HEIGHT = 48  // 指示器高度（px）
const PULL_THRESHOLD = 64    // 松手触发刷新的拉距（阻尼后）
const MAX_PULL = 96          // 指示器最大位移
const DAMPING = 0.5          // 拉距阻尼，模拟原生手感

function isTouchDevice(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return (
    window.matchMedia('(pointer: coarse)').matches ||
    window.matchMedia('(hover: none)').matches ||
    (navigator.maxTouchPoints ?? 0) > 0
  )
}

interface PullToRefreshProps {
  /** 刷新动作（返回 Promise；完成前指示器保持“刷新中”） */
  onRefresh: () => Promise<unknown> | unknown
  children: React.ReactNode
}

export function PullToRefresh({ onRefresh, children }: PullToRefreshProps) {
  const [enabled] = useState(isTouchDevice)
  const [offset, setOffset] = useState(0)
  const [armed, setArmed] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const startYRef = useRef<number | null>(null)
  const pullingRef = useRef(false)
  const armedRef = useRef(false)
  const refreshingRef = useRef(false)
  const onRefreshRef = useRef(onRefresh)
  useEffect(() => { onRefreshRef.current = onRefresh })

  useEffect(() => {
    if (!enabled) return
    const scroller = document.getElementById('main-content')
    if (!scroller) return

    const reset = () => {
      startYRef.current = null
      pullingRef.current = false
      armedRef.current = false
      setArmed(false)
      setDragging(false)
      setOffset(0)
    }

    const onTouchStart = (e: TouchEvent) => {
      if (refreshingRef.current) return
      if (scroller.scrollTop <= 0 && e.touches.length === 1) {
        startYRef.current = e.touches[0].clientY
      } else {
        startYRef.current = null
      }
    }

    const onTouchMove = (e: TouchEvent) => {
      if (startYRef.current === null || refreshingRef.current) return
      if (scroller.scrollTop > 0) {
        pullingRef.current = false
        armedRef.current = false
        setArmed(false)
        setDragging(false)
        setOffset(0)
        return
      }
      const delta = e.touches[0].clientY - startYRef.current
      if (delta <= 0) {
        reset()
        return
      }
      pullingRef.current = true
      setDragging(true)
      const damped = Math.min(MAX_PULL, delta * DAMPING)
      setOffset(damped)
      armedRef.current = damped >= PULL_THRESHOLD
      setArmed(armedRef.current)
    }

    const onTouchEnd = () => {
      if (!pullingRef.current) return
      if (armedRef.current && !refreshingRef.current) {
        refreshingRef.current = true
        setRefreshing(true)
        setDragging(false)
        setOffset(INDICATOR_HEIGHT)
        Promise.resolve(onRefreshRef.current()).finally(() => {
          refreshingRef.current = false
          reset()
        })
      } else {
        reset()
      }
    }

    const opts: AddEventListenerOptions = { passive: true }
    scroller.addEventListener('touchstart', onTouchStart, opts)
    scroller.addEventListener('touchmove', onTouchMove, opts)
    scroller.addEventListener('touchend', onTouchEnd, opts)
    scroller.addEventListener('touchcancel', onTouchEnd, opts)
    return () => {
      scroller.removeEventListener('touchstart', onTouchStart)
      scroller.removeEventListener('touchmove', onTouchMove)
      scroller.removeEventListener('touchend', onTouchEnd)
      scroller.removeEventListener('touchcancel', onTouchEnd)
    }
  }, [enabled])

  if (!enabled) return <>{children}</>

  return (
    <div className="relative">
      <div
        className="absolute inset-x-0 flex items-center justify-center gap-2 text-xs font-medium text-gray-500"
        style={{
          top: -INDICATOR_HEIGHT,
          height: INDICATOR_HEIGHT,
          transform: `translateY(${offset}px)`,
          // 拖动中指示器跟手（无过渡）；松手后平滑归位
          transition: dragging || refreshing ? 'none' : 'transform 200ms ease-out',
        }}
        aria-hidden={!refreshing}
      >
        {refreshing ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin text-primary-500" aria-hidden="true" />
            刷新中…
          </>
        ) : (
          <>
            <ArrowDown
              className={clsx('h-4 w-4 transition-transform', armed && 'rotate-180', armed && 'text-primary-500')}
              aria-hidden="true"
            />
            {armed ? '松手刷新' : '下拉刷新'}
          </>
        )}
      </div>
      {children}
    </div>
  )
}
