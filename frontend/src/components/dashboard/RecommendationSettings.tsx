/**
 * RecommendationSettings：推荐配置 UI。
 *
 * 简单模式：兴趣/平衡/最新/探索
 * 高级模式：权重调整
 */
import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Settings, Sliders, X } from 'lucide-react'
import { errorMessage } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import { userPrefsApi } from '../../api/user_prefs'
import { useModalA11y } from '../../hooks/useModalA11y'
import { ConfirmDialog } from '../ui/ConfirmDialog'

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
  exploration_first: '优先展示你还没接触过的来源与主题',
}

/** 五因子滑杆定义（顺序即展示顺序，键名与后端 weights 字段一致） */
const WEIGHT_SLIDERS = [
  { key: 'topic_match', label: '兴趣匹配', hint: '与「偏好设置」里兴趣主题的匹配程度' },
  { key: 'affinity', label: '阅读亲缘', hint: '你常打开的任务/平台，亲缘度随交互累积' },
  { key: 'recency', label: '新鲜度', hint: '按 24 小时半衰期衰减，越新越高' },
  { key: 'engagement', label: '参与度', hint: '对同类内容的阅读次数与停留时长' },
  { key: 'exploration', label: '探索度', hint: '你尚未接触过的来源与主题的新奇度' },
] as const

export function RecommendationSettings({ onClose }: RecommendationSettingsProps) {
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<PreferenceMode>('balanced')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [weights, setWeights] = useState({
    topic_match: 0.35,
    affinity: 0.3,
    recency: 0.2,
    engagement: 0.1,
    exploration: 0.05,
  })
  // 用户是否手动调过滑杆：隐藏高级设置后保存时也要把手调值一并提交，
  // 否则"调了权重 → 收起高级 → 保存"会静默退回模式预设（改了却不生效）
  const [weightsDirty, setWeightsDirty] = useState(false)
  // 用户是否已经动手改过（模式或滑杆）。配置请求比用户操作晚到时，
  // 回填逻辑不得覆盖刚做的选择——否则"打开设置立刻点一个模式"会被
  // 随后到达的已存配置静默重置回原模式
  const [userTouched, setUserTouched] = useState(false)
  // 有未保存修改时，关闭前必须让用户显式决定是否放弃
  const [confirmDiscardOpen, setConfirmDiscardOpen] = useState(false)

  // 关闭守卫：改过设置就弹丢弃确认，未改才直接关。
  // 保存成功走 onClose 直接退出（职责已完成），不经过这里。
  const requestClose = useCallback(() => {
    if (userTouched) {
      setConfirmDiscardOpen(true)
      return
    }
    onClose()
  }, [userTouched, onClose])

  // 焦点陷阱 + Escape 经 requestClose（有未保存修改时先确认丢弃）
  const modalRef = useModalA11y(requestClose)

  const configQuery = useQuery({
    queryKey: queryKeys.userPrefs.recommendationConfig(),
    queryFn: userPrefsApi.getRecommendationConfig,
  })

  // 回填已保存的配置，避免打开弹窗即显示默认值、保存时覆盖用户偏好。
  // 用"渲染期比较数据引用调整本地 state"（React 官方模式）而非 effect 回填
  const config = configQuery.data
  const [syncedConfig, setSyncedConfig] = useState(config)
  if (config && config !== syncedConfig) {
    setSyncedConfig(config)
    const cfg = config
    if (!userTouched) {
      if (cfg.preference_mode && cfg.preference_mode in MODE_LABELS) {
        setMode(cfg.preference_mode as PreferenceMode)
      }
      if (cfg.weights) {
        setWeights((prev) => ({
          topic_match: cfg.weights.topic_match ?? prev.topic_match,
          affinity: cfg.weights.affinity ?? prev.affinity,
          recency: cfg.weights.recency ?? prev.recency,
          engagement: cfg.weights.engagement ?? prev.engagement,
          exploration: cfg.weights.exploration ?? prev.exploration,
        }))
      }
    }
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      userPrefsApi.updateRecommendationConfig({
        preference_mode: mode,
        // 手调过权重就提交（哪怕高级面板已收起），未手调则只提交模式，
        // 由服务端展开预设——保证"所见即所存"
        weights: showAdvanced || weightsDirty ? weights : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.userPrefs.recommendationConfig() })
      // 推荐结果必须立刻失效重取：否则保存后列表最长 30s 仍是旧分数，
      // 用户无法确认新配置到底有没有生效
      queryClient.invalidateQueries({ queryKey: queryKeys.recommendations.all })
      toast.success('推荐设置已保存，推荐已按新权重刷新')
      onClose()
    },
  })

  const handleModeChange = (newMode: PreferenceMode) => {
    setMode(newMode)
    setUserTouched(true)
    // 切模式即回到预设权重，清掉手调标记（否则会把上一模式的手调值叠上去）
    setWeightsDirty(false)
    switch (newMode) {
      case 'interest_first':
        setWeights({ topic_match: 0.45, affinity: 0.30, recency: 0.10, engagement: 0.10, exploration: 0.05 })
        break
      case 'fresh_first':
        setWeights({ topic_match: 0.20, affinity: 0.10, recency: 0.50, engagement: 0.15, exploration: 0.05 })
        break
      case 'exploration_first':
        setWeights({ topic_match: 0.15, affinity: 0.10, recency: 0.20, engagement: 0.10, exploration: 0.45 })
        break
      default:
        setWeights({ topic_match: 0.35, affinity: 0.30, recency: 0.20, engagement: 0.10, exploration: 0.05 })
    }
  }

  /** 滑杆改动：更新值并标记手调（保存时不再被高级面板的显隐左右） */
  const updateWeight = (key: keyof typeof weights, value: number) => {
    setWeights((prev) => ({ ...prev, [key]: value }))
    setWeightsDirty(true)
    setUserTouched(true)
  }

  return (
    // 遮罩点击不关闭：本弹窗的职责是产出保存后的推荐配置，
    // 误点背景会让刚调的权重无声作废；退出只走关闭/取消/Esc（均带未保存确认）
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50">
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="recommendation-settings-title"
        className="bg-surface rounded-lg shadow-xl w-full max-w-lg mx-4"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-subtle">
          <h2 id="recommendation-settings-title" className="text-lg font-semibold text-primary flex items-center gap-2">
            <Settings className="h-5 w-5" />
            推荐设置
          </h2>
          <button onClick={requestClose} className="btn-ghost p-1" aria-label="关闭">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          <fieldset>
            <legend className="block text-sm font-medium text-secondary mb-2">
              偏好模式
            </legend>
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="偏好模式">
              {(Object.keys(MODE_LABELS) as PreferenceMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={mode === m}
                  onClick={() => handleModeChange(m)}
                  className={`p-3 border rounded-lg text-left transition-colors ${
                    mode === m
                      ? 'border-accent bg-accent-light'
                      : 'border-subtle hover:bg-hover'
                  }`}
                >
                  <div className="font-medium text-sm">{MODE_LABELS[m]}</div>
                  <div className="text-xs text-muted mt-1">{MODE_DESCRIPTIONS[m]}</div>
                </button>
              ))}
            </div>
          </fieldset>

          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              aria-expanded={showAdvanced}
              className="flex items-center gap-2 text-sm text-secondary hover:text-primary"
            >
              <Sliders className="h-4 w-4" />
              {showAdvanced ? '隐藏' : '显示'}高级设置
            </button>
          </div>

          {showAdvanced && (
            <fieldset className="space-y-3 p-4 bg-hover rounded-lg">
              <legend className="sr-only">权重调整</legend>
              {WEIGHT_SLIDERS.map(({ key, label, hint }) => (
                <div key={key}>
                  <label htmlFor={`weight-${key}`} className="block text-sm text-secondary mb-1">
                    {label}: {weights[key].toFixed(2)}
                  </label>
                  <input
                    id={`weight-${key}`}
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={weights[key]}
                    onChange={(e) => updateWeight(key, parseFloat(e.target.value))}
                    className="w-full"
                    aria-describedby={`weight-${key}-hint`}
                  />
                  <p id={`weight-${key}-hint`} className="text-xs text-muted mt-0.5">
                    {hint}
                  </p>
                </div>
              ))}
              <p className="text-xs text-muted pt-1 border-t border-subtle">
                分数按各权重之和归一化，调整比例只改变排序含义、不会让推荐分整体缩水。
              </p>
            </fieldset>
          )}

          {saveMutation.isError && (
            <div className="text-sm text-danger bg-danger-light rounded p-2" role="alert">
              {errorMessage(saveMutation.error, '保存失败，请重试')}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-subtle">
          <button type="button" onClick={requestClose} className="btn-ghost">
            取消
          </button>
          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            aria-busy={saveMutation.isPending}
            className="btn-primary"
          >
            {saveMutation.isPending ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      {confirmDiscardOpen && (
        <ConfirmDialog
          title="放弃未保存的推荐设置？"
          message="你对偏好模式或权重的修改还没有保存，关闭后这些修改会丢失。"
          confirmText="放弃修改"
          cancelText="继续编辑"
          onConfirm={onClose}
          onCancel={() => setConfirmDiscardOpen(false)}
        />
      )}
    </div>
  )
}
