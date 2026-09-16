import { useId, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Plus, Sparkles, ThumbsUp } from 'lucide-react'
import { clsx } from 'clsx'
import { userPrefsApi } from '../../api/user_prefs'
import { toast } from 'react-hot-toast'
import type { UserTopic, RecommendedTopic } from '../../types'
import { useModalA11y } from '../../hooks/useModalA11y'

const CATEGORY_LABELS: Record<string, string> = {
  ai: 'AI / 大模型',
  web: 'Web 开发',
  mobile: '移动端',
  devops: 'DevOps',
  custom: '自定义',
  other: '其他',
}

interface PreferenceModalProps {
  isOpen: boolean
  onClose: () => void
}

export function PreferenceModal({ isOpen, onClose }: PreferenceModalProps) {
  const [newTopic, setNewTopic] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('custom')
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
    queryKey: ['user-topics'],
    queryFn: userPrefsApi.listTopics,
    enabled: isOpen,
  })

  const { data: recommendedTopics = [], isLoading: recLoading } = useQuery({
    queryKey: ['recommended-topics'],
    queryFn: () => userPrefsApi.getRecommendedTopics({ limit: 15 }),
    enabled: isOpen,
  })

  const addTopicMutation = useMutation({
    mutationFn: (data: { topic: string; category: string }) =>
      userPrefsApi.addTopic(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['user-topics'] })
      qc.invalidateQueries({ queryKey: ['recommendations'] })
      toast.success('已添加偏好主题')
      setNewTopic('')
    },
    onError: () => toast.error('添加失败'),
  })

  const removeTopicMutation = useMutation({
    mutationFn: (topic: string) => userPrefsApi.removeTopic(topic),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['user-topics'] })
      qc.invalidateQueries({ queryKey: ['recommendations'] })
      toast.success('已移除偏好主题')
    },
    onError: () => toast.error('移除失败'),
  })

  const addRecommendedMutation = useMutation({
    mutationFn: (topic: RecommendedTopic) =>
      userPrefsApi.addTopic({ topic: topic.topic, category: topic.category, weight: 1.0 }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['user-topics'] })
      qc.invalidateQueries({ queryKey: ['recommendations'] })
      toast.success('已添加推荐主题')
    },
    onError: () => toast.error('添加失败'),
  })

  const handleAddTopic = () => {
    const topic = newTopic.trim()
    if (!topic) return
    addTopicMutation.mutate({ topic, category: selectedCategory })
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
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="px-2 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
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

          {/* 已添加的话题 */}
          {topics.length > 0 && (
            <div className="mb-5">
              <h3 className="text-xs font-medium text-gray-600 mb-2">我的话题</h3>
              <div className="flex flex-wrap gap-2">
                {topics.map((topic: UserTopic) => (
                  <span
                    key={topic.id}
                    className={clsx(
                      'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium',
                      'bg-primary-50 text-primary-700'
                    )}
                  >
                    {topic.topic}
                    <button
                      onClick={() => removeTopicMutation.mutate(topic.topic)}
                      className="ml-0.5 p-0.5 rounded-full hover:bg-primary-200 transition-colors"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 推荐话题 */}
          {recLoading ? (
            <div className="py-4 text-center text-sm text-gray-400">加载推荐中...</div>
          ) : recommendedTopics.length > 0 ? (
            <div>
              <div className="flex items-center gap-1 mb-2">
                <ThumbsUp className="h-3.5 w-3.5 text-primary-500" />
                <h3 className="text-xs font-medium text-gray-600">根据你的阅读历史推荐</h3>
              </div>
              <div className="flex flex-wrap gap-2">
                {recommendedTopics.map((rec: RecommendedTopic) => {
                  const isAdded = existingTopicsSet.has(rec.topic.toLowerCase())
                  return (
                    <button
                      key={rec.topic}
                      onClick={() => !isAdded && addRecommendedMutation.mutate(rec)}
                      disabled={isAdded}
                      className={clsx(
                        'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-colors',
                        isAdded
                          ? 'bg-gray-100 text-gray-400 cursor-default'
                          : 'bg-gray-50 text-gray-600 hover:bg-primary-50 hover:text-primary-700'
                      )}
                      title={`推荐指数：${Math.round(rec.score * 100)}%`}
                    >
                      {rec.topic}
                      {!isAdded && <Plus className="h-3 w-3" />}
                      {isAdded && <span className="text-[10px]">已添加</span>}
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
