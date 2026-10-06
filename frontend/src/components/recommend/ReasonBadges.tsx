/**
 * ReasonBadges：推荐理由徽章。
 *
 * 后端 explanation_generator 为每条推荐生成可解释原因
 * （{type, label}），这里按类型映射图标与配色，以小徽章展示。
 * 没有理由（数组为空/字段缺失）时渲染为 null，不占位。
 */
import { Compass, Eye, Flame, History, Clock, Sparkles } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { RecommendationReason } from '../../types'

const REASON_STYLES: Record<string, { Icon: LucideIcon; cls: string }> = {
  topic:       { Icon: Sparkles, cls: 'bg-primary-50 text-primary-700' },
  affinity:    { Icon: Eye,      cls: 'bg-blue-50 text-blue-700' },
  recency:     { Icon: Clock,    cls: 'bg-green-50 text-green-700' },
  engagement:  { Icon: History,  cls: 'bg-amber-50 text-amber-700' },
  thread:      { Icon: Flame,    cls: 'bg-red-50 text-red-700' },
  exploration: { Icon: Compass,  cls: 'bg-violet-50 text-violet-700' },
}

interface ReasonBadgesProps {
  reasons?: RecommendationReason[]
  /** 最多展示的条数，避免卡片被徽章淹没 */
  max?: number
}

export function ReasonBadges({ reasons, max = 3 }: ReasonBadgesProps) {
  if (!reasons?.length) return null

  return (
    <div className="flex flex-wrap items-center gap-1 mt-1.5">
      {reasons.slice(0, max).map((reason, index) => {
        const style = REASON_STYLES[reason.type] ?? {
          Icon: Sparkles,
          cls: 'bg-gray-100 text-gray-600',
        }
        const { Icon } = style
        return (
          <span
            key={`${reason.type}-${index}`}
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-medium ${style.cls}`}
          >
            <Icon className="h-3 w-3 shrink-0" />
            {reason.label}
          </span>
        )
      })}
    </div>
  )
}
