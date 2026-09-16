/**
 * ProfilePage：我的兴趣画像。
 *
 * 展示用户兴趣分布，支持管理。
 */
import { useQuery } from '@tanstack/react-query'
import { userPrefsApi } from '../api/user_prefs'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'
import { SkeletonList } from '../components/ui/Skeleton'

export function ProfilePage() {
  const { data: topics, isLoading: topicsLoading, isError: topicsError, refetch: refetchTopics } = useQuery({
    queryKey: ['user-topics'],
    queryFn: () => userPrefsApi.listTopics(),
  })

  const { data: affinities, isLoading: affinitiesLoading, isError: affinitiesError, refetch: refetchAffinities } = useQuery({
    queryKey: ['user-affinities'],
    queryFn: () => userPrefsApi.getAffinities(),
  })

  const isLoading = topicsLoading || affinitiesLoading
  const isError = topicsError || affinitiesError

  if (isError) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-6">
        <h1 className="text-2xl font-bold mb-6">我的画像</h1>
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
      <h1 className="text-2xl font-bold mb-6">我的画像</h1>

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
                    <span className="w-32 text-sm font-medium">{topic.topic}</span>
                    <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
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

          {/* 阅读亲缘度 */}
          <section>
            <h2 className="text-lg font-semibold mb-3">阅读偏好</h2>
            {affinities?.length ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {affinities.map((aff) => (
                  <div key={`${aff.affinity_type}:${aff.affinity_value}`} className="p-3 border rounded-lg">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium">{aff.affinity_value}</span>
                      <span className="text-sm text-gray-500">
                        {(aff.affinity_score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 capitalize">{aff.affinity_type}</div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty
                title="暂无阅读偏好"
                description="与内容互动后，系统会学习你的阅读偏好"
              />
            )}
          </section>
        </div>
      )}
    </div>
  )
}
