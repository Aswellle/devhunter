/**
 * DailyChart：近 7 日采集量趋势图。
 *
 * 基于 recharts 的折线图：
 * - 横轴始终展示完整 7 天日期（缺失日期补 0），空库时也渲染完整坐标系，
 *   而不是"暂无数据"占位文字；
 * - 纵轴显示采集量刻度（整数，全 0 时仍给出 0–4 的参考刻度）；
 * - 附带趋势摘要文字与屏幕阅读器替代数据表。
 */
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'

interface DataPoint {
  date: string // YYYY-MM-DD
  count: number
}

interface DailyChartProps {
  data: DataPoint[]
}

/** 生成最近 7 天（含今天）的日期序列，缺失的日期补 0。 */
function fillLast7Days(data: DataPoint[]): DataPoint[] {
  const byDate: Record<string, number> = {}
  for (const d of data) byDate[d.date] = d.count
  const days: DataPoint[] = []
  const today = new Date()
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    days.push({ date: key, count: byDate[key] ?? 0 })
  }
  return days
}

export function DailyChart({ data }: DailyChartProps) {
  const series = fillLast7Days(data)
  const totalCount = series.reduce((sum, d) => sum + d.count, 0)
  const peak = series.reduce((max, d) => (d.count > max.count ? d : max), series[0])
  const summary =
    totalCount > 0
      ? `近 7 日共采集 ${totalCount} 条，峰值 ${peak.date.slice(5).replace('-', '/')}（${peak.count} 条）`
      : '近 7 日暂无采集数据'

  return (
    <div role="img" aria-label={`每日采集量趋势图：${summary}`}>
      <div style={{ width: '100%', height: 200 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
            <XAxis
              dataKey="date"
              tickFormatter={(iso) => iso.slice(5).replace('-', '/')}
              tick={{ fontSize: 11, fill: '#6B7280' }}
              tickLine={false}
              axisLine={{ stroke: '#E5E7EB' }}
            />
            <YAxis
              allowDecimals={false}
              domain={[0, (dataMax: number) => Math.max(4, Math.ceil(dataMax * 1.2))]}
              tick={{ fontSize: 11, fill: '#6B7280' }}
              tickLine={false}
              axisLine={false}
              width={46}
              label={{
                value: '采集量',
                angle: -90,
                position: 'insideLeft',
                offset: 4,
                style: { fontSize: 11, fill: '#9CA3AF' },
              }}
            />
            <Tooltip
              labelFormatter={(label) => `日期：${label}`}
              formatter={(value) => [`${value} 条`, '采集量']}
              contentStyle={{
                borderRadius: 8,
                border: '1px solid #E5E7EB',
                fontSize: 12,
                boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
              }}
            />
            <Line
              type="monotone"
              dataKey="count"
              name="采集量"
              stroke="#2563EB"
              strokeWidth={2}
              dot={{ r: 3, strokeWidth: 2, fill: '#FFFFFF' }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-muted mt-2">{summary}</p>
      {/* 屏幕阅读器替代数据表 */}
      <table className="sr-only">
        <caption>近 7 日每日采集量</caption>
        <thead>
          <tr>
            <th scope="col">日期</th>
            <th scope="col">采集量</th>
          </tr>
        </thead>
        <tbody>
          {series.map((d) => (
            <tr key={d.date}>
              <td>{d.date}</td>
              <td>{d.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
