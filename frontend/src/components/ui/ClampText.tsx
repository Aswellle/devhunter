import { useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

interface ClampTextProps {
  /** 需要截断的文本（null/undefined/空串不渲染） */
  text: string | null | undefined
  /** 折叠时的行数，默认 2 */
  lines?: number
  className?: string
  /** 展开按钮的文案主体（默认"摘要"） */
  label?: string
}

/**
 * 与 Tailwind line-clamp 等价的截断样式。
 * 行数由 props 决定，不走 Tailwind JIT（动态类名不会被扫描生成）。
 */
function clampStyle(lines: number): CSSProperties {
  return {
    display: '-webkit-box',
    WebkitLineClamp: lines,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  }
}

/**
 * 可展开的截断文本：
 * 仅当文本真的被截断（scrollHeight 超出 clientHeight）时才渲染
 * 「展开/收起」按钮，未截断的短文本保持纯展示、无多余控件。
 */
export function ClampText({ text, lines = 2, className, label = '摘要' }: ClampTextProps) {
  const [expanded, setExpanded] = useState(false)
  const [clamped, setClamped] = useState(false)
  const pRef = useRef<HTMLParagraphElement>(null)

  useLayoutEffect(() => {
    const el = pRef.current
    if (!el) return
    // +1 容忍亚像素取整误差，避免恰好一行溢出时误判
    setClamped(el.scrollHeight > el.clientHeight + 1)
  }, [text])

  if (!text) return null

  return (
    <div>
      <p
        ref={pRef}
        className={className}
        style={expanded ? undefined : clampStyle(lines)}
      >
        {text}
      </p>
      {clamped && (
        <button
          type="button"
          onClick={() => setExpanded(e => !e)}
          aria-expanded={expanded}
          className="mt-0.5 inline-flex items-center gap-0.5 text-xs text-gray-400 hover:text-primary-600 transition-colors"
        >
          {expanded ? (
            <>
              收起{label}
              <ChevronUp className="h-3 w-3" aria-hidden="true" />
            </>
          ) : (
            <>
              展开{label}
              <ChevronDown className="h-3 w-3" aria-hidden="true" />
            </>
          )}
        </button>
      )}
    </div>
  )
}
