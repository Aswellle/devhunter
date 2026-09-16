import { useQuery } from '@tanstack/react-query'
import { Activity, CheckCircle, Download, RefreshCw, Zap } from 'lucide-react'
import { statsApi } from '../../api/stats'
import { Spinner } from '../ui/Spinner'

interface StatCardProps {
  label: string
  value: string | number
  icon: React.ReactNode
  sub?: string
  colorClass?: string
}

function StatCard({ label, value, icon, sub, colorClass = 'text-gray-900' }: StatCardProps) {
  return (
    <div className="card px-4 py-3 flex items-center gap-3">
      <span className="text-gray-400">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs text-gray-500 leading-tight">{label}</p>
        <p className={`text-xl font-bold leading-tight ${colorClass}`}>{value}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

export function StatsCards() {
  const { data, isLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: statsApi.get,
    refetchInterval: 60_000,
  })

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card px-4 py-3 h-16 flex items-center justify-center">
            <Spinner className="h-4 w-4" />
          </div>
        ))}
      </div>
    )
  }

  if (!data) return null

  const successRateStr =
    data.success_rate_7d != null
      ? `${(data.success_rate_7d * 100).toFixed(0)}%`
      : 'N/A'

  const successColor =
    data.success_rate_7d == null ? 'text-gray-400' :
    data.success_rate_7d >= 0.9 ? 'text-green-600' :
    data.success_rate_7d >= 0.7 ? 'text-yellow-600' : 'text-red-500'

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <StatCard
        label="今日采集"
        value={data.items_today.toLocaleString()}
        icon={<Download className="h-5 w-5" />}
        sub={`总计 ${data.total_items.toLocaleString()} 条`}
      />
      <StatCard
        label="运行中任务"
        value={data.tasks.active}
        icon={<Zap className="h-5 w-5" />}
        sub={
          data.tasks.error > 0
            ? `${data.tasks.error} 个错误`
            : data.tasks.paused > 0
            ? `${data.tasks.paused} 个暂停`
            : `共 ${data.tasks.total} 个`
        }
        colorClass={data.tasks.error > 0 ? 'text-red-600' : 'text-gray-900'}
      />
      <StatCard
        label="今日执行"
        value={data.executions_today}
        icon={<RefreshCw className="h-5 w-5" />}
        sub={`7 日共 ${data.total_executions_7d} 次`}
      />
      <StatCard
        label="7 日成功率"
        value={successRateStr}
        icon={<CheckCircle className="h-5 w-5" />}
        sub={data.failures_7d > 0 ? `${data.failures_7d} 次失败` : '运行良好'}
        colorClass={successColor}
      />
    </div>
  )
}
