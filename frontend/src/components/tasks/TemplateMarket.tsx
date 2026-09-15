/**
 * TemplateMarket：模板市场式体验。

 * 按类别分组展示预设模板，支持一键启用。
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
    queryFn: () => tasksApi.templates(),
  })

  const templateList: SourceTemplate[] = templates || []

  const enableMutation = useMutation({
    mutationFn: (template: SourceTemplate) =>
      tasksApi.create({
        name: template.name,
        source_url: template.source_url,
        selector_list: template.selector_list,
        selector_title: template.selector_title,
        selector_link: template.selector_link,
        selector_summary: template.selector_summary,
        keywords: template.default_keywords,
        cron_expression: template.recommended_cron,
        template_id: template.id,
      }),
    onSuccess: (_data, variables) => {
      setEnabledTemplates((prev) => new Set(prev).add(variables.id))
      onCreated?.()
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
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-5xl mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b shrink-0">
          <h2 className="text-lg font-semibold">模板市场</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
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

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
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
                                className="flex items-center gap-1 px-2 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:opacity-50"
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
