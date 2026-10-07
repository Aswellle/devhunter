import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Globe, Search, Eye, Check, Loader2, AlertCircle } from 'lucide-react'
import { sourcesApi } from '../../api/sources'
import { tasksApi } from '../../api/tasks'
import { queryKeys } from '../../api/queryKeys'
import { errorMessage } from '../../api/client'
import { useModalA11y } from '../../hooks/useModalA11y'
import type { DiscoveryResult, PreviewResult } from '../../types'

interface SourceWizardProps {
  onClose: () => void
  onCreated?: () => void
}

type Step = 1 | 2 | 3

export function SourceWizard({ onClose, onCreated }: SourceWizardProps) {
  const qc = useQueryClient()
  const [step, setStep] = useState<Step>(1)
  const [url, setUrl] = useState('')
  const [discoveryResult, setDiscoveryResult] = useState<DiscoveryResult | null>(null)
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null)
  const [name, setName] = useState('')
  const [keywords, setKeywords] = useState('')
  const [cronExpression, setCronExpression] = useState('0 9 * * *')
  const [error, setError] = useState('')
  // 焦点陷阱 + Escape 关闭（组件随模态打开条件挂载）
  const modalRef = useModalA11y(onClose)

  const discoverMutation = useMutation({
    mutationFn: () => sourcesApi.discover(url),
    onSuccess: (data) => {
      // 发现接口对"抓不到/被拦截/结构识别失败"返回 200 + errors 清单：
      // 有错误时留在第一步并显示原因，否则用户会在第二步面对一排 N/A 选择器不知所措
      if (data.errors?.length) {
        setError(data.errors.join('；'))
        setDiscoveryResult(null)
        return
      }
      setDiscoveryResult(data)
      // 用站点标题预填任务名称（用户已输入或站点无名时保持现状）
      if (!name && data.title) {
        setName(data.title)
      }
      // URL 变了就重新发现，旧 URL 的预览结果必须作废，
      // 否则"继续"按钮会用上一个 URL 的 preview.success 放行
      setPreviewResult(null)
      setStep(2)
    },
    onError: (e: unknown) => {
      // 拦截器产出的是 ApiError（非 Error 实例），用 errorMessage 提取后端具体文案
      setError(errorMessage(e, '发现失败，请检查 URL 是否正确'))
    },
  })

  const previewMutation = useMutation({
    mutationFn: () => sourcesApi.preview(url, discoveryResult || undefined),
    onSuccess: (data) => {
      setPreviewResult(data)
    },
    onError: (e: unknown) => {
      setError(errorMessage(e, '预览失败'))
    },
  })

  const saveMutation = useMutation({
    mutationFn: () =>
      tasksApi.create({
        name,
        source_url: url,
        template_id: null,
        selector_list: discoveryResult?.list_selector || '',
        selector_title: discoveryResult?.title_selector || '',
        selector_link: discoveryResult?.link_selector || '',
        selector_summary: discoveryResult?.summary_selector || null,
        selector_next_page: null,
        keywords: keywords ? keywords.split(/[,，]/).map((k) => k.trim()).filter(Boolean) : [],
        cron_expression: cronExpression,
        // 自定义来源默认讨论型；条目型可在任务设置里改
        content_kind: 'discussion',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.tasks.all })
      onCreated?.()
      onClose()
    },
    onError: (e: unknown) => {
      setError(errorMessage(e, '保存失败'))
    },
  })

  const handleDiscover = () => {
    if (!url) return
    setError('')
    discoverMutation.mutate()
  }

  const handlePreview = () => {
    setError('')
    previewMutation.mutate()
  }

  const handleSave = () => {
    setError('')
    // 自动发现失败/未产出选择器时不允许保存：空 selector 过去会打到
    // 数据库 NOT NULL 约束上返回 500，现在前后端都拦（后端返回 400）
    if (!discoveryResult?.list_selector || !discoveryResult?.title_selector || !discoveryResult?.link_selector) {
      setError('未获取到有效的选择器，请返回上一步重新执行「自动发现」')
      return
    }
    saveMutation.mutate()
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-wizard-title"
        className="bg-surface rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-subtle">
          <h2 id="source-wizard-title" className="text-lg font-semibold text-primary">
            添加新数据源
          </h2>
          <button onClick={onClose} className="text-muted hover:text-secondary" aria-label="关闭">
            ✕
          </button>
        </div>


        <div className="px-6 py-3 bg-gray-50 border-b">
          <div className="flex items-center gap-2">
            <StepIndicator step={1} current={step} label="输入 URL" />
            <div className="flex-1 h-px bg-gray-300" />
            <StepIndicator step={2} current={step} label="自动发现" />
            <div className="flex-1 h-px bg-gray-300" />
            <StepIndicator step={3} current={step} label="确认保存" />
          </div>
        </div>

        <div className="px-6 py-4">
          {error && (
            <div role="alert" className="mb-4 p-3 bg-danger-light border border-danger/20 rounded-lg flex items-center gap-2 text-danger">
              <AlertCircle className="h-4 w-4" />
              <span className="text-sm">{error}</span>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  网站 URL
                </label>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Globe className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <input
                      type="url"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="https://example.com"
                      className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                      autoFocus
                    />
                  </div>
                  <button
                    onClick={handleDiscover}
                    disabled={!url || discoverMutation.isPending}
                    className="btn-primary px-4 py-2 rounded-lg flex items-center gap-2"
                  >
                    {discoverMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Search className="h-4 w-4" />
                    )}
                    发现
                  </button>
                </div>
              </div>
              <p className="text-sm text-gray-500">
                输入网站 URL，系统将自动检测其内容结构。
              </p>
            </div>
          )}

          {step === 2 && discoveryResult && (
            <div className="space-y-4">
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <Globe className="h-4 w-4 text-blue-600" />
                  <span className="font-medium text-blue-900">
                    检测到 {discoveryResult.source_type?.toUpperCase?.() || 'HTML'}
                  </span>
                </div>
                {discoveryResult.title && (
                  <p className="text-sm text-blue-800">{discoveryResult.title}</p>
                )}
                {discoveryResult.description && (
                  <p className="text-sm text-blue-700 mt-1">{discoveryResult.description}</p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-gray-500">列表:</span>
                  <code className="ml-2 px-2 py-0.5 bg-gray-100 rounded text-xs">
                    {discoveryResult.list_selector || 'N/A'}
                  </code>
                </div>
                <div>
                  <span className="text-gray-500">标题:</span>
                  <code className="ml-2 px-2 py-0.5 bg-gray-100 rounded text-xs">
                    {discoveryResult.title_selector || 'N/A'}
                  </code>
                </div>
                <div>
                  <span className="text-gray-500">链接:</span>
                  <code className="ml-2 px-2 py-0.5 bg-gray-100 rounded text-xs">
                    {discoveryResult.link_selector || 'N/A'}
                  </code>
                </div>
                <div>
                  <span className="text-gray-500">摘要:</span>
                  <code className="ml-2 px-2 py-0.5 bg-gray-100 rounded text-xs">
                    {discoveryResult.summary_selector || 'N/A'}
                  </code>
                </div>
              </div>

              <div>
                <button
                  onClick={handlePreview}
                  disabled={previewMutation.isPending}
                  className="btn-ghost w-full px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center justify-center gap-2"
                >
                  {previewMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                  预览条目
                </button>
              </div>

              {previewResult?.error && (
                <div role="alert" className="p-3 bg-danger-light border border-danger/20 rounded-lg flex items-start gap-2 text-danger text-sm">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <span className="break-all">{previewResult.error}</span>
                </div>
              )}

              {previewResult?.items && previewResult.items.length > 0 && (
                <div className="border rounded-lg overflow-hidden">
                  <div className="px-3 py-2 bg-gray-50 border-b text-sm font-medium">
                    预览（{previewResult.items.length} 条{previewResult.total_found > previewResult.items.length ? `，共 ${previewResult.total_found} 条` : ''}）
                  </div>
                  <div className="max-h-60 overflow-y-auto">
                    {previewResult.items.map((item, i) => (
                      <div key={i} className="px-3 py-2 border-b last:border-b-0 text-sm">
                        <div className="font-medium truncate">{item.title}</div>
                        <div className="text-gray-500 truncate text-xs">{item.url}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {previewResult && !previewResult.error && previewResult.items.length === 0 && (
                <p className="text-sm text-gray-500">
                  页面可以访问，但没有提取到条目——该页面可能不是列表页，可尝试换用列表页 URL。
                </p>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => setStep(1)}
                  className="btn-ghost flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  上一步
                </button>
                <button
                  onClick={() => setStep(3)}
                  disabled={!previewResult?.success || previewResult.items.length === 0}
                  className="btn-primary flex-1 px-4 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  继续
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  任务名称
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={discoveryResult?.title || '新数据源'}
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  关键词（可选，逗号分隔）
                </label>
                <input
                  type="text"
                  value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                  placeholder="AI, Rust, SaaS"
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  更新频率
                </label>
                <select
                  value={cronExpression}
                  onChange={(e) => setCronExpression(e.target.value)}
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="*/30 * * * *">每 30 分钟</option>
                  <option value="0 * * * *">每小时</option>
                  <option value="0 */6 * * *">每 6 小时</option>
                  <option value="0 9 * * *">每天</option>
                  <option value="0 9 * * 1">每周</option>
                </select>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => setStep(2)}
                  className="btn-ghost flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  上一步
                </button>
                <button
                  onClick={handleSave}
                  disabled={saveMutation.isPending || !name.trim()}
                  title={name.trim() ? undefined : '请先填写任务名称'}
                  className="btn-primary flex-1 px-4 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {saveMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Check className="h-4 w-4" />
                  )}
                  保存
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StepIndicator({ step, current, label }: { step: number; current: Step; label: string }) {
  const isActive = step === current
  const isDone = step < current
  return (
    <div className="flex items-center gap-1.5">
      <div
        className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
          isDone
            ? 'bg-green-500 text-white'
            : isActive
              ? 'bg-blue-600 text-white'
              : 'bg-gray-200 text-gray-500'
        }`}
      >
        {isDone ? '✓' : step}
      </div>
      <span className={`text-xs ${isActive ? 'font-medium text-blue-600' : 'text-gray-500'}`}>
        {label}
      </span>
    </div>
  )
}
