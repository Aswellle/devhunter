/**
 * RecommendationSettings：推荐配置 UI。
 *
 * 简单模式：兴趣/平衡/最新/探索
 * 高级模式：权重调整
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Settings, Sliders } from 'lucide-react'
import { userPrefsApi } from '../../api/user_prefs'

interface RecommendationSettingsProps {
  onClose: () => void
}

type PreferenceMode = 'interest_first' | 'balanced' | 'fresh_first' | 'exploration_first'

const MODE_LABELS: Record<PreferenceMode, string> = {
  interest_first: '兴趣优先',
  balanced: '平衡模式',
  fresh_first: '最新优先',
  exploration_first: '探索发现',
}

const MODE_DESCRIPTIONS: Record<PreferenceMode, string> = {
  interest_first: '优先展示与你的兴趣和阅读历史匹配的内容',
  balanced: '平衡兴趣、新鲜内容和探索发现',
  fresh_first: '优先展示最新的内容',
  exploration_first: '发现新的主题和数据源',
}

export function RecommendationSettings({ onClose }: RecommendationSettingsProps) {
  const [mode, setMode] = useState<PreferenceMode>('balanced')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [weights, setWeights] = useState({
    topic_match: 0.4,
    affinity: 0.3,
    recency: 0.2,
    engagement: 0.1,
  })

  const saveMutation = useMutation({
    mutationFn: () =>
      userPrefsApi.updateRecommendationConfig({
        preference_mode: mode,
        weights: showAdvanced ? weights : undefined,
      }),
    onSuccess: () => {
      onClose()
    },
  })

  const handleModeChange = (newMode: PreferenceMode) => {
    setMode(newMode)
    switch (newMode) {
      case 'interest_first':
        setWeights({ topic_match: 0.5, affinity: 0.3, recency: 0.1, engagement: 0.1 })
        break
      case 'fresh_first':
        setWeights({ topic_match: 0.2, affinity: 0.1, recency: 0.5, engagement: 0.2 })
        break
      case 'exploration_first':
        setWeights({ topic_match: 0.2, affinity: 0.1, recency: 0.2, engagement: 0.1 })
        break
      default:
        setWeights({ topic_match: 0.4, affinity: 0.3, recency: 0.2, engagement: 0.1 })
    }
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Settings className="h-5 w-5" />
            推荐设置
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            ✕
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              偏好模式
            </label>
            <div className="grid grid-cols-2 gap-2">
              {(Object.keys(MODE_LABELS) as PreferenceMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => handleModeChange(m)}
                  className={`p-3 border rounded-lg text-left transition-colors ${
                    mode === m
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <div className="font-medium text-sm">{MODE_LABELS[m]}</div>
                  <div className="text-xs text-gray-500 mt-1">{MODE_DESCRIPTIONS[m]}</div>
                </button>
              ))}
            </div>
          </div>

          <div>
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
            >
              <Sliders className="h-4 w-4" />
              {showAdvanced ? '隐藏' : '显示'}高级设置
            </button>
          </div>

          {showAdvanced && (
            <div className="space-y-3 p-4 bg-gray-50 rounded-lg">
              <div>
                <label className="block text-sm text-gray-600 mb-1">
                  主题匹配权重: {weights.topic_match.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={weights.topic_match}
                  onChange={(e) => setWeights({ ...weights, topic_match: parseFloat(e.target.value) })}
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">
                  亲缘度权重: {weights.affinity.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={weights.affinity}
                  onChange={(e) => setWeights({ ...weights, affinity: parseFloat(e.target.value) })}
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">
                  新鲜度权重: {weights.recency.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={weights.recency}
                  onChange={(e) => setWeights({ ...weights, recency: parseFloat(e.target.value) })}
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">
                  参与度权重: {weights.engagement.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={weights.engagement}
                  onChange={(e) => setWeights({ ...weights, engagement: parseFloat(e.target.value) })}
                  className="w-full"
                />
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t">
          <button onClick={onClose} className="btn-ghost">
            取消
          </button>
          <button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} className="btn-primary">
            {saveMutation.isPending ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}
