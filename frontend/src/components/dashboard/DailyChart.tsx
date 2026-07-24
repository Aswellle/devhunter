interface DataPoint {
  date: string
  count: number
}

interface DailyChartProps {
  data: DataPoint[]
}

export function DailyChart({ data }: DailyChartProps) {
  if (!data.length) {
    return (
      <div className="h-24 flex items-center justify-center text-xs text-gray-400">
        暂无数据
      </div>
    )
  }

  const W = 420
  const H = 88
  const LABEL_H = 18
  const BAR_AREA_H = H - LABEL_H - 10
  const maxCount = Math.max(...data.map((d) => d.count), 1)
  const n = data.length
  const barW = Math.min(36, (W - 16) / n - 4)
  const step = (W - 16) / n

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      style={{ height: '88px' }}
      aria-label="每日采集量趋势图"
    >
      {data.map((d, i) => {
        const barH = Math.max(2, (d.count / maxCount) * BAR_AREA_H)
        const x = 8 + i * step + (step - barW) / 2
        const y = H - LABEL_H - barH

        return (
          <g key={d.date}>
            {/* 柱体 */}
            <rect
              x={x} y={y}
              width={barW} height={barH}
              rx={3}
              className="fill-primary-500"
              opacity={0.82}
            />
            {/* 数量标注（仅非零时显示） */}
            {d.count > 0 && (
              <text
                x={x + barW / 2} y={y - 3}
                textAnchor="middle"
                fontSize="9"
                fill="#6b7280"
              >
                {d.count}
              </text>
            )}
            {/* 日期标注：显示 MM/DD */}
            <text
              x={x + barW / 2}
              y={H - 3}
              textAnchor="middle"
              fontSize="9"
              fill="#9ca3af"
            >
              {d.date.slice(5).replace('-', '/')}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
