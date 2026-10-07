import { clsx } from 'clsx'
import { RECOMMENDED_BADGE_SCORE } from '../../utils/scores'

/**
 * 分级配色的推荐分胶囊：
 * ≥80 强推荐（主题色）、≥60 扎实（中性）、其余静默灰。
 * 分级边界与 RECOMMENDED_BADGE_SCORE 对齐——胶囊变主题色即"推荐"态，
 * 调用方传 0-100 的整数即可，组件内不做换算。
 */
const TIERS = [
  { min: RECOMMENDED_BADGE_SCORE, className: 'bg-primary-50 text-primary-700 ring-primary-200' },
  { min: 60, className: 'bg-gray-100 text-gray-700 ring-gray-200' },
  { min: 0, className: 'bg-gray-50 text-gray-400 ring-gray-100' },
]

interface ScorePillProps {
  /** 0-100 的整数分值 */
  score: number
  /** 紧凑模式：只显示数字（用于仪表盘等密集列表） */
  compact?: boolean
  className?: string
}

export function ScorePill({ score, compact = false, className }: ScorePillProps) {
  const value = Math.round(score)
  const tier = TIERS.find((t) => value >= t.min) ?? TIERS[TIERS.length - 1]

  return (
    <span
      title={`推荐分 ${value}/100`}
      aria-label={`推荐分 ${value} 分`}
      className={clsx(
        'inline-flex h-5 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2 ring-1 ring-inset',
        tier.className,
        className,
      )}
    >
      {!compact && (
        <>
          <span className="text-[11px] font-medium leading-none opacity-80">推荐分</span>
          <span className="h-2.5 w-px bg-current opacity-25" aria-hidden="true" />
        </>
      )}
      <span className="font-mono text-[12.5px] font-bold leading-none tabular-nums">{value}</span>
    </span>
  )
}
