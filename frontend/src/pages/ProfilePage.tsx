/**
 * ProfilePage：我的兴趣画像。
 *
 * 展示用户兴趣分布，支持管理。
 */
import { useQuery } from '@tanstack/react-query'
import { userPrefsApi } from '../api/user_prefs'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'

export function ProfilePage() {
  const { data: topics, isLoading: topicsLoading } = useQuery({
    queryKey: ['user-topics'],
    queryFn: () => userPrefsApi.listTopics(),
  })

  const { data: affinities, isLoading: affinitiesLoading } = useQuery({
    queryKey: ['user-affinities'],
    queryFn: () => userPrefsApi.getAffinities(),
  })

  const isLoading = topicsLoading || affinitiesLoading

  return (
    <div className="max-w-4xl mx-auto px-6 py-6">
      <h1 className="text-2xl font-bold mb-6">Your Interest Profile</h1>

      {isLoading ? (
        <div className="flex justify-center py-20">
          <Spinner className="h-8 w-8" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Topics */}
          <section>
            <h2 className="text-lg font-semibold mb-3">Topics</h2>
            {topics?.length ? (
              <div className="space-y-2">
                {topics.map((topic: any) => (
                  <div key={topic.topic} className="flex items-center gap-3">
                    <span className="w-32 text-sm font-medium">{topic.topic}</span>
                    <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 rounded-full"
                        style={{ width: `${(topic.weight || 0) * 100}%` }}
                      />
                    </div>
                    <span className="w-12 text-sm text-gray-500 text-right">
                      {((topic.weight || 0) * 100).toFixed(0)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <Empty
                title="No Topics Yet"
                description="Start reading to build your profile."
              />
            )}
          </section>

          {/* Affinities */}
          <section>
            <h2 className="text-lg font-semibold mb-3">Reading Affinities</h2>
            {affinities?.length ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {affinities.map((aff: any) => (
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
                title="No Affinities Yet"
                description="Interact with content to build your profile."
              />
            )}
          </section>
        </div>
      )}
    </div>
  )
}
