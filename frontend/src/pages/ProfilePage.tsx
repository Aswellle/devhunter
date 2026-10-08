/**
 * ProfilePage：我的兴趣画像。
 *
 * 展示用户兴趣分布，支持管理。
 */
import { useQuery } from '@tanstack/react-query'
import { Copy, Check } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'react-hot-toast'
import { userPrefsApi } from '../api/user_prefs'
import { feedsApi } from '../api/feeds'
import { queryKeys } from '../api/queryKeys'
import { formatDistanceToNow } from '../utils/time'
import { Empty } from '../components/ui/Empty'
import { SkeletonList } from '../components/ui/Skeleton'
import { LLMSetupCard } from '../components/profile/LLMSetupCard'
import { LabelingAssistant } from '../components/profile/LabelingAssistant'
import type { AffinityEntry, FeedInfo } from '../types'

// 展示维度 → 中文标签（后端已把 task/platform 归一为 task）
const AFFINITY_TYPE_LABELS: Record<string, string> = {
  task: '任务',
  keyword: '关键词',
}

/** 复制到剪贴板（ insecure 上下文回退 execCommand） */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // 非 HTTPS / 非安全上下文时 clipboard API 不可用
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  }
}

/** 单条订阅地址行：名称 + 截断 URL + 复制按钮 */
function FeedRow({ name, url }: { name: string; url: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    if (await copyText(url)) {
      setCopied(true)
      toast.success('订阅地址已复制')
      setTimeout(() => setCopied(false), 1500)
    } else {
      toast.error('复制失败，请手动复制')
    }
  }

  return (
    <div className="flex items-center gap-3 py-2">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-gray-800">{name}</div>
        <div className="text-xs text-gray-400 font-mono truncate" title={url}>
          {url}
        </div>
      </div>
      <button
        type="button"
        onClick={handleCopy}
        aria-label={`复制 ${name} 的订阅地址`}
        className="btn-ghost px-2 py-1.5 shrink-0"
      >
        {copied
          ? <Check className="h-4 w-4 text-success" aria-hidden="true" />
          : <Copy className="h-4 w-4" aria-hidden="true" />}
      </button>
    </div>
  )
}

export function ProfilePage() {
  const { data: topics, isLoading: topicsLoading, isError: topicsError, refetch: refetchTopics } = useQuery({
    queryKey: queryKeys.userPrefs.topics(),
    queryFn: () => userPrefsApi.listTopics(),
  })

  const { data: affinities, isLoading: affinitiesLoading, isError: affinitiesError, refetch: refetchAffinities } = useQuery({
    queryKey: queryKeys.recommendations.affinities(),
    queryFn: () => userPrefsApi.getAffinities(),
  })

  // RSS 订阅地址（辅助信息，不阻塞页面主体）
  const { data: feedOverview, isLoading: feedsLoading } = useQuery({
    queryKey: queryKeys.feeds.overview(),
    queryFn: () => feedsApi.getOverview(),
    staleTime: 60_000,
  })

  const isLoading = topicsLoading || affinitiesLoading
  const isError = topicsError || affinitiesError

  if (isError) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-6">
        <h1 className="text-xl font-bold text-gray-900">我的画像</h1>
        <p className="text-sm text-gray-500 mt-0.5 mb-6">你的兴趣主题与阅读偏好</p>
        <Empty
          title="加载失败"
          description="画像数据加载出错，请检查网络连接后重试"
          action={
            <button onClick={() => { refetchTopics(); refetchAffinities() }} className="btn-primary">
              重试
            </button>
          }
        />
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-6">
      <h1 className="text-xl font-bold text-gray-900">我的画像</h1>
      <p className="text-sm text-gray-500 mt-0.5 mb-6">你的兴趣主题与阅读偏好</p>

      {isLoading ? (
        <SkeletonList count={4} />
      ) : (
        <div className="space-y-6">
          {/* 主题偏好 */}
          <section>
            <h2 className="text-lg font-semibold mb-3">兴趣主题</h2>
            {topics?.length ? (
              <div className="space-y-2">
                {topics.map((topic) => (
                  <div key={topic.topic} className="flex items-center gap-3">
                    <span className="w-32 shrink-0 truncate text-sm font-medium" title={topic.topic}>
                      {topic.topic}
                    </span>
                    <div
                      className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden"
                      role="progressbar"
                      aria-valuenow={Math.round((topic.weight || 0) * 100)}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`${topic.topic} 兴趣权重`}
                    >
                      <div
                        className="h-full bg-blue-500 rounded-full"
                        style={{ width: `${Math.min(100, (topic.weight || 0) * 100)}%` }}
                      />
                    </div>

                    <span className="w-12 text-sm text-gray-500 text-right">
                      {((topic.weight || 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <Empty
                title="暂无兴趣主题"
                description="阅读内容后，系统会自动分析你的兴趣偏好"
              />
            )}
          </section>

          {/* 阅读偏好 */}
          <section>
            <h2 className="text-lg font-semibold mb-1">阅读偏好</h2>
            <p className="text-xs text-gray-500 mb-3">
              根据你的浏览、点击、收藏行为按时间衰减累积。百分比以列表中互动最多的来源为
              100% 基准，表示相对偏好强度，不是绝对占比。
            </p>
            {affinities?.length ? (() => {
              const maxScore = Math.max(...affinities.map((a) => a.affinity_score), 0)
              return (
                <div className="space-y-4">
                  {affinities.map((aff: AffinityEntry) => {
                    const name = aff.display_value ?? aff.affinity_value
                    const rawType = aff.display_type ?? aff.affinity_type
                    const typeLabel = AFFINITY_TYPE_LABELS[rawType] ?? rawType
                    // 相对偏好强度：以互动最多的来源为 100% 基准（原始分是无上限的衰减累积值）
                    const relPct = maxScore > 0
                      ? Math.max(1, Math.round((aff.affinity_score / maxScore) * 100))
                      : 0
                    return (
                      <div
                        key={aff.id}
                        className="flex items-start gap-3"
                        title={`偏好分 ${aff.affinity_score.toFixed(2)}（衰减累积值）`}
                      >
                        <span className="badge badge-gray shrink-0 mt-0.5">{typeLabel}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <span className="text-sm font-medium truncate" title={name}>
                              {name}
                            </span>
                            <span className="text-sm text-gray-600 shrink-0">{relPct}%</span>
                          </div>
                          <div
                            className="h-2 bg-gray-100 rounded-full overflow-hidden"
                            role="progressbar"
                            aria-valuenow={relPct}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-label={`${name} 相对偏好强度`}
                          >
                            <div
                              className="h-full bg-blue-500 rounded-full"
                              style={{ width: `${relPct}%` }}
                            />
                          </div>
                          <div className="text-xs text-gray-400 mt-1">
                            {aff.interaction_count} 次互动 · 最近 {formatDistanceToNow(aff.last_interacted_at)}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )
            })() : (
              <Empty
                title="暂无阅读偏好"
                description="与内容互动后，系统会学习你的阅读偏好"
              />
            )}
          </section>

          {/* 推荐质量打标 */}
          <LabelingAssistant />

          {/* RSS 订阅 */}
          <section>
            <h2 className="text-lg font-semibold mb-1">RSS 订阅</h2>
            <p className="text-xs text-gray-500 mb-3">
              在任意 RSS 阅读器中订阅采集内容。链接包含你的私有访问令牌，请勿外传；
              轮换服务端 SECRET_KEY 可使其全部失效。
            </p>
            {feedsLoading ? (
              <SkeletonList count={1} />
            ) : feedOverview ? (
              <div className="card px-4 py-1 divide-y divide-gray-100">
                <FeedRow name="全部采集" url={feedOverview.all_url} />
                {feedOverview.feeds.map((f: FeedInfo) => (
                  <FeedRow key={f.task_id} name={f.task_name} url={f.url} />
                ))}
              </div>
            ) : (
              <Empty
                title="订阅地址加载失败"
                description="请刷新页面重试"
              />
            )}
          </section>

          {/* AI 接入 */}
          <LLMSetupCard />
        </div>
      )}
    </div>
  )
}
