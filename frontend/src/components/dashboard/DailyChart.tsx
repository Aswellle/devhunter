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
      <div className="h-24 flex items-center justify-center text-xs text-muted" role="status">
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

  // 生成趋势摘要
  const totalCount = data.reduce((sum, d) => sum + d.count, 0)
  const peakDate = data.reduce((max, d) => d.count > max.count ? d : max, data[0])
  const summary = `近 ${n} 日共采集 ${totalCount} 条，峰值 ${peakDate.date.slice(5).replace('-', '/')}（${peakDate.count} 条）`

  return (
    <>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ height: '88px' }}
        role="img"
        aria-label={`每日采集量趋势图：${summary}`}
      >
        <title>每日采集量趋势图</title>
        <desc>{summary}</desc>
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
      {/* 屏幕阅读器替代数据表 */}
      <table className="sr-only">
        <caption>每日采集量详细数据</caption>
        <thead>
          <tr><th>日期</th><th>采集量</th></tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.date}>
              <td>{d.date}</td>
              <td>{d.count} 条</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
