/**
 * TemplateMarket：模板市场式体验。

 * 分类展示预设模板，支持一键启用。
 */
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Zap, ExternalLink, Check } from 'lucide-react'
import { tasksApi } from '../../api/tasks'
import { Spinner } from '../../components/ui/Spinner'

interface TemplateMarketProps {
  onClose: () => void
  onCreated?: () => void
}

interface PresetTemplate {
  id: string
  name: string
  description: string
  source_url: string
  recommended_cron: string
}

const CATEGORIES = [
  { id: 'all', name: 'All' },
  { id: 'ai', name: 'AI & ML' },
  { id: 'dev', name: 'Developer' },
  { id: 'startup', name: 'Startup' },
  { id: 'chinese', name: 'Chinese' },
]

export function TemplateMarket({ onClose, onCreated }: TemplateMarketProps) {
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [enabledTemplates, setEnabledTemplates] = useState<Set<string>>(new Set())

  const { data: templates, isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: () => tasksApi.templates(),
  })

  const templateList = templates || []

  const enableMutation = useMutation({
    mutationFn: (template: PresetTemplate) =>
      tasksApi.create({
        name: template.name,
        source_url: template.source_url,
        selector_list: '',
        selector_title: '',
        selector_link: '',
        keywords: [],
        cron_expression: template.recommended_cron,
        template_id: template.id,
      }),
    onSuccess: (_data, variables) => {
      setEnabledTemplates((prev) => new Set(prev).add(variables.id))
      onCreated?.()
    },
  })

  const filteredTemplates = templateList.filter((t: PresetTemplate) => {
    if (selectedCategory === 'all') return true
    const name = t.name.toLowerCase()
    if (selectedCategory === 'ai') return name.includes('ai') || name.includes('gpt') || name.includes('llm')
    if (selectedCategory === 'dev') return name.includes('github') || name.includes('hackernews') || name.includes('dev')
    if (selectedCategory === 'startup') return name.includes('indie') || name.includes('startup')
    if (selectedCategory === 'chinese') return name.includes('v2ex') || name.includes('掘金') || name.includes('少数派')
    return true
  })

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-lg font-semibold">Template Market</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            ✕
          </button>
        </div>

        <div className="px-6 py-3 border-b bg-gray-50">
          <div className="flex gap-2">
            {CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                onClick={() => setSelectedCategory(cat.id)}
                className={`px-3 py-1 rounded-full text-sm ${
                  selectedCategory === cat.id
                    ? 'bg-blue-600 text-white'
                    : 'bg-white border hover:bg-gray-50'
                }`}
              >
                {cat.name}
              </button>
            ))}
          </div>
        </div>

        <div className="px-6 py-4">
          {isLoading ? (
            <div className="flex justify-center py-10">
              <Spinner className="h-8 w-8" />
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {filteredTemplates.map((template: PresetTemplate) => {
                const isEnabled = enabledTemplates.has(template.id)
                return (
                  <div
                    key={template.id}
                    className="p-4 border rounded-lg hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <h3 className="font-medium">{template.name}</h3>
                      {isEnabled ? (
                        <span className="flex items-center gap-1 text-green-600 text-sm">
                          <Check className="h-4 w-4" />
                          Enabled
                        </span>
                      ) : (
                        <button
                          onClick={() => enableMutation.mutate(template)}
                          disabled={enableMutation.isPending}
                          className="flex items-center gap-1 px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
                        >
                          {enableMutation.isPending ? (
                            <Spinner className="h-3 w-3" />
                          ) : (
                            <Zap className="h-3 w-3" />
                          )}
                          Enable
                        </button>
                      )}
                    </div>
                    <p className="text-sm text-gray-600 mb-2">{template.description}</p>
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      <ExternalLink className="h-3 w-3" />
                      <span className="truncate">{template.source_url}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
