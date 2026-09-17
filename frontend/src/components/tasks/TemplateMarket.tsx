/**
 * TemplateMarket：模板市场模态框。
 *
 * 按类别分组展示预设模板，支持一键启用。
 * 模态框使用固定宽高，避免切换类别时视口摇晃。
 */
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Zap, ExternalLink, Check, Code, Lightbulb, Users, BookOpen, Palette, ClipboardList } from 'lucide-react'
import { tasksApi } from '../../api/tasks'
import { Spinner } from '../../components/ui/Spinner'
import type { SourceTemplate } from '../../types'

interface TemplateMarketProps {
  onClose: () => void
  onCreated?: () => void
}

const CATEGORIES = [
  { id: 'all', name: '全部', icon: null },
  { id: '开发趋势', name: '开发趋势', icon: Code },
  { id: '创意发现', name: '创意发现', icon: Lightbulb },
  { id: '社区讨论', name: '社区讨论', icon: Users },
  { id: '技术博客', name: '技术博客', icon: BookOpen },
  { id: '内容创作', name: '内容创作', icon: Palette },
  { id: '需求分享', name: '需求分享', icon: ClipboardList },
]

export function TemplateMarket({ onClose, onCreated }: TemplateMarketProps) {
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [enabledTemplates, setEnabledTemplates] = useState<Set<string>>(new Set())

  const { data: templates, isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: tasksApi.templates,
  })

  const templateList: SourceTemplate[] = templates || []

  const enableMutation = useMutation({
    mutationFn: (tpl: SourceTemplate) =>
      tasksApi.create({
        name: tpl.name,
        source_url: tpl.source_url,
        template_id: tpl.id,
        selector_list: tpl.selector_list,
        selector_title: tpl.selector_title,
        selector_link: tpl.selector_link,
        selector_summary: tpl.selector_summary ?? null,
        selector_next_page: null,
        keywords: tpl.default_keywords || [],
        cron_expression: tpl.recommended_cron,
      }),
    onSuccess: (data) => {
      setEnabledTemplates((prev) => new Set([...prev, data.id]))
      onCreated?.()
    },
    onError: (err) => {
      console.error('[TemplateMarket] 启用模板失败:', err)
    },
  })

  const filteredTemplates = templateList.filter((t: SourceTemplate) => {
    if (selectedCategory === 'all') return true
    return t.category === selectedCategory
  })

  // Group templates by category
  const groupedTemplates: Record<string, SourceTemplate[]> = {}
  for (const t of filteredTemplates) {
    const cat = t.category || '其他'
    if (!groupedTemplates[cat]) groupedTemplates[cat] = []
    groupedTemplates[cat].push(t)
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="template-market-title"
        className="bg-surface rounded-lg shadow-xl w-[900px] h-[600px] max-w-[90vw] max-h-[85vh] flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-subtle shrink-0">
          <h2 id="template-market-title" className="text-lg font-semibold text-primary">
            模板市场
          </h2>
          <button onClick={onClose} className="text-muted hover:text-secondary" aria-label="关闭">
            ✕
          </button>
        </div>


        {/* Categories */}
        <div className="px-6 py-3 border-b bg-gray-50 shrink-0">
          <div className="flex gap-2 flex-wrap">
            {CATEGORIES.map((cat) => {
              const Icon = cat.icon
              return (
                <button
                  key={cat.id}
                  onClick={() => setSelectedCategory(cat.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm transition-colors ${
                    selectedCategory === cat.id
                      ? 'bg-blue-600 text-white'
                      : 'bg-white border hover:bg-gray-50'
                  }`}
                >
                  {Icon && <Icon className="h-3.5 w-3.5" />}
                  {cat.name}
                </button>
              )
            })}
          </div>
        </div>

        {/* Content - Fixed height scrollable area */}
        <div className="flex-1 overflow-y-auto px-6 py-4" style={{ minHeight: '400px' }}>
          {isLoading ? (
            <div className="flex justify-center py-10">
              <Spinner className="h-8 w-8" />
            </div>
          ) : (
            <div className="space-y-6">
              {Object.entries(groupedTemplates).map(([category, items]) => (
                <div key={category}>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                    {category}
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {items.map((template: SourceTemplate) => {
                      const isEnabled = enabledTemplates.has(template.id)
                      return (
                        <div
                          key={template.id}
                          className="p-4 border rounded-lg hover:shadow-md transition-shadow"
                        >
                          <div className="flex items-start justify-between mb-2">
                            <h4 className="font-medium text-sm">{template.name}</h4>
                            {isEnabled ? (
                              <span className="flex items-center gap-1 text-green-600 text-xs">
                                <Check className="h-3 w-3" />
                                已启用
                              </span>
                            ) : (
                              <button
                                onClick={() => enableMutation.mutate(template)}
                                disabled={enableMutation.isPending}
                                className="btn-primary flex items-center gap-1 px-2 py-1 text-xs"
                              >
                                {enableMutation.isPending ? (
                                  <Spinner className="h-3 w-3" />
                                ) : (
                                  <Zap className="h-3 w-3" />
                                )}
                                启用
                              </button>
                            )}
                          </div>
                          <p className="text-xs text-gray-600 mb-2 line-clamp-2">{template.description}</p>
                          <div className="flex items-center gap-2 text-xs text-gray-500">
                            <ExternalLink className="h-3 w-3" />
                            <span className="truncate">{template.source_url}</span>
                          </div>
                          {template.subcategory && (
                            <span className="inline-block mt-2 px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded">
                              {template.subcategory}
                            </span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
