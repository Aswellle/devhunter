import { useQuery } from '@tanstack/react-query'
import { statsApi } from '../api/stats'
import { StatsCards } from '../components/dashboard/StatsCards'
import { DailyChart } from '../components/dashboard/DailyChart'
import { Spinner } from '../components/ui/Spinner'

export function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: statsApi.get,
    refetchInterval: 60_000,
  })

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-gray-900">数据概览</h1>
        <p className="text-sm text-gray-500 mt-0.5">采集系统运行状态与数据统计</p>
      </div>

      {/* KPI 卡片 */}
      <StatsCards />

      {/* 每日采集趋势 */}
      <div className="card p-4">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">近 7 日采集量趋势</h2>
        {isLoading ? (
          <div className="h-24 flex items-center justify-center">
            <Spinner />
          </div>
        ) : (
          <DailyChart data={data?.daily_items ?? []} />
        )}
      </div>

      {/* 下方两列：活跃任务排行 + 任务状态 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

        {/* Top Tasks */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">
            近 7 日采集量 Top 5
          </h2>
          {isLoading ? (
            <div className="flex justify-center py-6"><Spinner /></div>
          ) : !data?.top_tasks_7d.length ? (
            <p className="text-xs text-gray-400 py-4 text-center">暂无数据</p>
          ) : (
            <div className="space-y-2">
              {data.top_tasks_7d.map((t, i) => {
                const maxCount = data.top_tasks_7d[0]?.item_count || 1
                const pct = Math.round((t.item_count / maxCount) * 100)
                return (
                  <div key={t.name} className="flex items-center gap-2">
                    <span className="text-xs text-gray-400 w-4 shrink-0">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-xs font-medium text-gray-700 truncate">
                          {t.name}
                        </span>
                        <span className="text-xs text-primary-600 ml-2 shrink-0">
                          {t.item_count}
                        </span>
                      </div>
                      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary-500 rounded-full transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* 任务状态分布 */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">任务状态分布</h2>
          {isLoading ? (
            <div className="flex justify-center py-6"><Spinner /></div>
          ) : !data ? null : (
            <div className="space-y-3">
              {[
                { label: '运行中',  value: data.tasks.active,  color: 'bg-green-500',  text: 'text-green-700' },
                { label: '已暂停',  value: data.tasks.paused,  color: 'bg-gray-400',   text: 'text-gray-600' },
                { label: '错误状态', value: data.tasks.error,  color: 'bg-red-500',    text: 'text-red-600' },
              ].map((row) => {
                const total = data.tasks.total || 1
                const pct = Math.round((row.value / total) * 100)
                return (
                  <div key={row.label}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className={`font-medium ${row.text}`}>{row.label}</span>
                      <span className="text-gray-500">{row.value} 个 ({pct}%)</span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${row.color} rounded-full transition-all`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                )
              })}

              <div className="pt-2 border-t border-gray-100 text-xs text-gray-500">
                共 <b className="text-gray-700">{data.tasks.total}</b> 个任务
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}