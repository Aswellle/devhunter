import { useState } from 'react'
import { createPortal } from 'react-dom'
import { Settings } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { statsApi } from '../api/stats'
import { queryKeys } from '../api/queryKeys'
import { StatsCards } from '../components/dashboard/StatsCards'
import { DailyChart } from '../components/dashboard/DailyChart'
import { ForYouSection } from '../components/dashboard/ForYouSection'
import { PreferenceModal } from '../components/dashboard/PreferenceModal'
import { RecommendationSettings } from '../components/dashboard/RecommendationSettings'
import { PullToRefresh } from '../components/ui/PullToRefresh'
import { StickySectionNav } from '../components/ui/StickySectionNav'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'

/** 仪表盘分区（模块级常量：引用稳定，StickySectionNav 的 effect 依赖它） */
const DASH_SECTIONS = [
  { id: 'dash-overview', label: '概览' },
  { id: 'dash-foryou', label: '为你推荐' },
  { id: 'dash-trend', label: '采集趋势' },
  { id: 'dash-tasks', label: '任务统计' },
]

export function DashboardPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: queryKeys.stats.all,
    queryFn: statsApi.get,
    refetchInterval: (query) => {
      // 上一次拉取失败时暂停自动轮询（页面已有重试按钮）；
      // errorUpdateCount 是累计值、成功后不清零，用它会让一次网络抖动永久关闭轮询
      if (query.state.status === 'error') return false
      return 60_000
    },
  })

  const qc = useQueryClient()
  // 移动端下拉刷新：统计 + 推荐流一并重取
  const handlePullRefresh = () => Promise.allSettled([
    refetch(),
    qc.invalidateQueries({ queryKey: queryKeys.recommendations.all }),
  ])

  const [preferencesOpen, setPreferencesOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  return (
    <PullToRefresh onRefresh={handlePullRefresh}>
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-gray-900">数据概览</h1>
        <p className="text-sm text-gray-500 mt-0.5">采集系统运行状态与数据统计</p>
      </div>

      <StickySectionNav sections={DASH_SECTIONS} />

      {/* U3: stats failing to load previously rendered every card as its
          own silent "no data" empty state, with no indication that
          anything actually went wrong (vs. a genuinely empty install). */}
      {isError ? (
        <Empty
          title="数据加载失败"
          description="统计数据加载出错，请检查网络连接后重试"
          action={
            <button onClick={() => refetch()} className="btn-primary">
              重试
            </button>
          }
        />
      ) : (
        <>
          {/* KPI 卡片 */}
          <div id="dash-overview" className="scroll-mt-14">
            <StatsCards />
          </div>

          {/* 为你推荐 */}
          <div id="dash-foryou" className="scroll-mt-14">
            <ForYouSection onOpenPreferences={() => setPreferencesOpen(true)} />
          </div>
          {preferencesOpen && createPortal(
            <PreferenceModal isOpen={preferencesOpen} onClose={() => setPreferencesOpen(false)} />,
            document.body
          )}

          {settingsOpen && createPortal(
            <RecommendationSettings onClose={() => setSettingsOpen(false)} />,
            document.body
          )}
          {/* 每日采集趋势（推荐设置入口收进卡片右上角，避免把卡片间距拉开） */}
          <div id="dash-trend" className="card p-4 scroll-mt-14">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-700">近 7 日采集量趋势</h2>
              <button
                onClick={() => setSettingsOpen(true)}
                className="flex items-center gap-1 text-xs text-gray-500 hover:text-primary transition-colors"
              >
                <Settings className="h-3.5 w-3.5" />
                推荐设置
              </button>
            </div>
            <div style={{ minHeight: '88px' }}>
              {isLoading ? (
                <div className="h-24 flex items-center justify-center">
                  <Spinner />
                </div>
              ) : (
                <DailyChart data={data?.daily_items ?? []} />
              )}
            </div>
          </div>

          {/* 下方两列：活跃任务排行 + 任务状态 */}
          <div id="dash-tasks" className="grid grid-cols-1 sm:grid-cols-2 gap-4 scroll-mt-14">

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
                      <div key={t.id} className="flex items-center gap-2">
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
        </>
      )}
    </div>
    </PullToRefresh>
  )
}
