import { useId, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Plus, Sparkles, ThumbsUp, Minus, Info } from 'lucide-react'
import { clsx } from 'clsx'
import { userPrefsApi } from '../../api/user_prefs'
import { queryKeys } from '../../api/queryKeys'
import { errorMessage } from '../../api/client'
import { toast } from 'react-hot-toast'
import type { UserTopic, RecommendedTopic } from '../../types'
import { useModalA11y } from '../../hooks/useModalA11y'

/** 主题权重步进与边界（权重参与「兴趣匹配」占比计算） */
const WEIGHT_STEP = 0.25
const WEIGHT_MIN = 0.25
const WEIGHT_MAX = 3

interface PreferenceModalProps {
  isOpen: boolean
  onClose: () => void
}

export function PreferenceModal({ isOpen, onClose }: PreferenceModalProps) {
  const [newTopic, setNewTopic] = useState('')
  const qc = useQueryClient()
  const titleId = useId()
  // Hooks must run unconditionally every render (rules-of-hooks), so this
  // is called before the `if (!isOpen) return null` guard below. Passing
  // `isOpen` explicitly matters here — unlike TaskFormModal (which mounts
  // fresh each time it opens via conditional rendering), this component
  // stays mounted and toggles visibility through the `isOpen` prop, so the
  // hook's effect must re-run when `isOpen` flips rather than only on mount.
  const modalRef = useModalA11y(onClose, isOpen)

  const { data: topics = [] } = useQuery({
    queryKey: queryKeys.userPrefs.topics(),
    queryFn: userPrefsApi.listTopics,
    enabled: isOpen,
  })

  const { data: recommendedTopics = [], isLoading: recLoading } = useQuery({
    queryKey: queryKeys.recommendations.topics(),
    queryFn: () => userPrefsApi.getRecommendedTopics({ limit: 15 }),
    enabled: isOpen,
  })

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: queryKeys.userPrefs.topics() })
    // 主题变化会改变推荐排序（兴趣匹配因子），列表立即重取
    qc.invalidateQueries({ queryKey: queryKeys.recommendations.all })
    qc.invalidateQueries({ queryKey: queryKeys.items.all })
  }

  const addTopicMutation = useMutation({
    mutationFn: (data: { topic: string; category: string; weight?: number }) =>
      userPrefsApi.addTopic(data),
    onSuccess: () => {
      invalidateAll()
      toast.success('已添加，推荐列表已按新兴趣重排')
      setNewTopic('')
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '添加失败')),
  })

  const removeTopicMutation = useMutation({
    mutationFn: (topic: string) => userPrefsApi.removeTopic(topic),
    onSuccess: () => {
      invalidateAll()
      toast.success('已移除偏好主题')
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '移除失败')),
  })

  const weightMutation = useMutation({
    mutationFn: (payload: { topic: string; weight: number }) =>
      userPrefsApi.updateTopicWeight(payload.topic, payload.weight),
    onSuccess: () => {
      invalidateAll()
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '权重调整失败')),
  })

  const addRecommendedMutation = useMutation({
    mutationFn: (topic: RecommendedTopic) =>
      userPrefsApi.addTopic({ topic: topic.topic, category: topic.category, weight: 1.0 }),
    onSuccess: (_, topic) => {
      invalidateAll()
      toast.success(`已添加「${topic.topic}」，推荐列表已按新兴趣重排`)
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '添加失败')),
  })

  const handleAddTopic = () => {
    const topic = newTopic.trim()
    if (!topic) return
    // 分类已不暴露给用户（对推荐无影响），统一存 custom
    addTopicMutation.mutate({ topic, category: 'custom' })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleAddTopic()
    }
  }

  if (!isOpen) return null

  const existingTopicsSet = new Set(topics.map((t: UserTopic) => t.topic.toLowerCase()))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative w-full max-w-lg mx-4 bg-white rounded-2xl shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-primary-400 to-primary-600 flex items-center justify-center">
              <Sparkles className="h-4 w-4 text-white" />
            </div>
            <div>
              <h2 id={titleId} className="text-base font-semibold text-gray-900">兴趣偏好设置</h2>
              <p className="text-xs text-gray-500">设置你感兴趣的话题，我们会为你推荐相关内容</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            aria-label="关闭"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* 添加后到底有什么效果：把作用链路说清楚 */}
        <div className="px-5 py-2 bg-blue-50/70 border-b border-blue-100 flex items-start gap-1.5">
          <Info className="h-3.5 w-3.5 mt-0.5 shrink-0 text-blue-500" aria-hidden="true" />
          <p className="text-xs text-blue-800 leading-relaxed">
            添加的话题会参与「为你推荐」的<b>兴趣匹配</b>打分（权重可在「推荐设置」中调节）：
            标题或摘要命中话题词的内容会得到更高推荐分并前置。权重越高，该话题对排序影响越大。
          </p>
        </div>

        {/* Content */}
        <div className="px-5 py-4 max-h-[60vh] overflow-y-auto">
          {/* 添加新话题 */}
          <div className="mb-5">
            <label className="block text-xs font-medium text-gray-600 mb-2">添加新话题</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={newTopic}
                onChange={(e) => setNewTopic(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="例如：GPT-5、AI创业、React 18..."
                className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              />
              <button
                onClick={handleAddTopic}
                disabled={!newTopic.trim() || addTopicMutation.isPending}
                className={clsx(
                  'px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-1',
                  newTopic.trim()
                    ? 'bg-primary-600 text-white hover:bg-primary-700'
                    : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                )}
              >
                <Plus className="h-4 w-4" />
                添加
              </button>
            </div>
          </div>

          {/* 已添加的话题：可调权重 */}
          {topics.length > 0 && (
            <div className="mb-5">
              <h3 className="text-xs font-medium text-gray-600 mb-2">
                我的话题 <span className="font-normal text-gray-400">· 权重参与兴趣匹配占比</span>
              </h3>
              <div className="space-y-1.5">
                {topics.map((topic: UserTopic) => {
                  const weight = topic.weight ?? 1
                  return (
                    <div
                      key={topic.id}
                      className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-primary-50/60"
                    >
                      <span className="flex-1 min-w-0 truncate text-sm font-medium text-primary-800" title={topic.topic}>
                        {topic.topic}
                      </span>
                      {/* 权重步进：直接对应后端 updateTopicWeight（此前 API 存在但界面无入口） */}
                      <div className="flex items-center gap-0.5 shrink-0">
                        <button
                          type="button"
                          onClick={() => weightMutation.mutate({
                            topic: topic.topic,
                            weight: Math.max(WEIGHT_MIN, Math.round((weight - WEIGHT_STEP) * 100) / 100),
                          })}
                          disabled={weight <= WEIGHT_MIN || weightMutation.isPending}
                          className="p-1 rounded text-primary-600 hover:bg-primary-100 disabled:opacity-30"
                          aria-label={`降低「${topic.topic}」权重`}
                        >
                          <Minus className="h-3 w-3" aria-hidden="true" />
                        </button>
                        <span className="w-9 text-center text-xs font-mono tabular-nums text-primary-700" title="主题权重">
                          ×{weight.toFixed(2)}
                        </span>
                        <button
                          type="button"
                          onClick={() => weightMutation.mutate({
                            topic: topic.topic,
                            weight: Math.min(WEIGHT_MAX, Math.round((weight + WEIGHT_STEP) * 100) / 100),
                          })}
                          disabled={weight >= WEIGHT_MAX || weightMutation.isPending}
                          className="p-1 rounded text-primary-600 hover:bg-primary-100 disabled:opacity-30"
                          aria-label={`提高「${topic.topic}」权重`}
                        >
                          <Plus className="h-3 w-3" aria-hidden="true" />
                        </button>
                      </div>
                      <button
                        onClick={() => removeTopicMutation.mutate(topic.topic)}
                        className="p-1 rounded hover:bg-primary-200 transition-colors shrink-0"
                        aria-label={`移除「${topic.topic}」`}
                      >
                        <X className="h-3 w-3 text-primary-700" />
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* 推荐话题 */}
          {recLoading ? (
            <div className="py-4 text-center text-sm text-gray-400">加载推荐中...</div>
          ) : recommendedTopics.length > 0 ? (
            <div>
              <div className="flex items-center gap-1 mb-1">
                <ThumbsUp className="h-3.5 w-3.5 text-primary-500" />
                <h3 className="text-xs font-medium text-gray-600">根据你的阅读历史推荐</h3>
              </div>
              <p className="text-[11px] text-gray-400 mb-2">
                从你常读来源的高频标题词与阅读关键词中提取，点选即添加
              </p>
              <div className="flex flex-wrap gap-2">
                {recommendedTopics.map((rec: RecommendedTopic) => {
                  const isAdded = existingTopicsSet.has(rec.topic.toLowerCase())
                  return (
                    <button
                      key={rec.topic}
                      onClick={() => !isAdded && addRecommendedMutation.mutate(rec)}
                      disabled={isAdded || addRecommendedMutation.isPending}
                      className={clsx(
                        'inline-flex flex-col items-start gap-0.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors text-left',
                        isAdded
                          ? 'bg-gray-100 text-gray-400 cursor-default'
                          : 'bg-gray-50 text-gray-700 hover:bg-primary-50 hover:text-primary-700'
                      )}
                      title={`推荐指数 ${Math.round(rec.score * 100)}%${rec.reason ? ` · ${rec.reason}` : ''}`}
                    >
                      <span className="inline-flex items-center gap-1">
                        {rec.topic}
                        {!isAdded && <Plus className="h-3 w-3" />}
                        {isAdded && <span className="text-[10px]">已添加</span>}
                      </span>
                      {/* 来源说明：用户能看懂这条推荐从哪来 */}
                      <span className="text-[10px] font-normal text-gray-400">
                        {rec.reason || '来自你的阅读历史'}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          ) : (
            <div className="py-4 text-center">
              <p className="text-sm text-gray-400">
                暂无推荐话题，浏览更多内容后我们会为你推荐
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 bg-gray-50 border-t border-gray-100 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-800 transition-colors"
          >
            完成
          </button>
        </div>
      </div>
    </div>
  )
}
