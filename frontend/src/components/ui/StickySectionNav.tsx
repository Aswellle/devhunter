/**
 * StickySectionNav.tsx
 * 粘性锚点导航：PillTabs 风格 + scroll-spy。
 *
 * - 吸顶于滚动容器（#main-content）顶部，毛玻璃底
 * - scroll-spy：滚动时高亮当前分区；点按平滑滚到分区（尊重
 *   prefers-reduced-motion），滚动期间抑制 spy 抖动
 * - 用容器坐标手动计算落点并预留导航条自身高度，避免分区顶部
 *   被粘性条遮住（不依赖调用方给分区加 scroll-margin）
 */
import { useEffect, useRef, useState } from 'react'
import { clsx } from 'clsx'

export interface NavSection {
  id: string
  label: string
}

interface StickySectionNavProps {
  /** 分区清单（顺序即页面顺序）；建议传模块级常量保持引用稳定 */
  sections: NavSection[]
  /** 滚动容器元素 id，默认布局的 main-content */
  containerId?: string
}

/** 导航条自身高度 + 呼吸间距：点按跳转时分区的落点偏移 */
const NAV_CLEARANCE = 56
/** spy 判定线：分区顶部越过容器顶部下方 96px 即视为到达 */
const SPY_LINE = 96
/** 平滑滚动期间跳过的 scroll 事件数（每帧一个，约 1 秒量级） */
const CLICK_SKIP_EVENTS = 60

export function StickySectionNav({ sections, containerId = 'main-content' }: StickySectionNavProps) {
  const [active, setActive] = useState(sections[0]?.id ?? '')
  // 点按跳转后跳过若干 scroll 事件，抑制平滑滚动路径上 spy 的中途高亮；
  // scrollend（Chromium/Safari 均已支持）到达时立即解除
  const skipSpyRef = useRef(0)
  // 为让末节够到锚位而补的容器底部内边距——卸载时还原为此前的内联值
  const padRestoreRef = useRef<string | null>(null)

  useEffect(() => {
    const container = document.getElementById(containerId)
    if (!container) return

    const onScroll = () => {
      if (skipSpyRef.current > 0) {
        skipSpyRef.current -= 1
        return
      }
      const containerTop = container.getBoundingClientRect().top
      let current = sections[0]?.id ?? ''
      for (const s of sections) {
        const el = document.getElementById(s.id)
        if (!el) continue
        if (el.getBoundingClientRect().top - containerTop <= SPY_LINE) {
          current = s.id
        }
      }
      // 滚到底强制选中最后一节（末节内容不足一屏时 spy 永远到不了它）
      if (container.scrollTop + container.clientHeight >= container.scrollHeight - 2) {
        current = sections[sections.length - 1]?.id ?? current
      }
      setActive((prev) => (prev === current ? prev : current))
    }

    const onScrollEnd = () => { skipSpyRef.current = 0 }

    onScroll()
    container.addEventListener('scroll', onScroll, { passive: true })
    container.addEventListener('scrollend', onScrollEnd)
    return () => {
      container.removeEventListener('scroll', onScroll)
      container.removeEventListener('scrollend', onScrollEnd)
    }
  }, [sections, containerId])

  // 离开页面时还原点按跳转补出的容器底部内边距
  useEffect(() => {
    const container = document.getElementById(containerId)
    return () => {
      if (container && padRestoreRef.current !== null) {
        container.style.paddingBottom = padRestoreRef.current
        padRestoreRef.current = null
      }
    }
  }, [containerId])

  const go = (id: string) => {
    const el = document.getElementById(id)
    const container = document.getElementById(containerId)
    if (!el || !container) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const target =
      container.scrollTop +
      el.getBoundingClientRect().top -
      container.getBoundingClientRect().top -
      NAV_CLEARANCE
    // 末节下方内容不足一屏时，浏览器滚不到锚位（上限 = scrollHeight - clientHeight）。
    // 按差额补足容器底部内边距，让目标分区真正到达视口锚位；离开页面时还原。
    const maxScroll = container.scrollHeight - container.clientHeight
    if (target > maxScroll) {
      const computedPad = parseFloat(window.getComputedStyle(container).paddingBottom) || 0
      if (padRestoreRef.current === null) {
        padRestoreRef.current = container.style.paddingBottom
      }
      container.style.paddingBottom = `${computedPad + (target - maxScroll)}px`
    }
    container.scrollTo({ top: Math.max(0, target), behavior: reduced ? 'auto' : 'smooth' })
    skipSpyRef.current = CLICK_SKIP_EVENTS
    setActive(id)
    // 更新 hash 但不触发跳转
    window.history.replaceState(null, '', `#${id}`)
  }

  return (
    <nav
      aria-label="页面分区"
      className="sticky top-0 z-20 py-2 bg-gray-50/90 backdrop-blur-md"
    >
      <div className="flex items-center gap-1 w-fit p-1 bg-gray-200/60 rounded-lg">
        {sections.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => go(s.id)}
            aria-current={active === s.id ? 'true' : undefined}
            className={clsx(
              'px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-all',
              'focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-inset outline-none',
              active === s.id
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700',
            )}
          >
            {s.label}
          </button>
        ))}
      </div>
    </nav>
  )
}
