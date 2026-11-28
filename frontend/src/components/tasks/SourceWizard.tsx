import { useCallback, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Globe, Search, Eye, Check, Loader2, AlertCircle, Lightbulb, ArrowRightLeft } from 'lucide-react'
import { sourcesApi } from '../../api/sources'
import { tasksApi } from '../../api/tasks'
import { queryKeys } from '../../api/queryKeys'
import { errorMessage } from '../../api/client'
import { useModalA11y } from '../../hooks/useModalA11y'
import { ConfirmDialog } from '../ui/ConfirmDialog'
import { SchedulePicker } from './SchedulePicker'
import type { DiscoveryFailure, DiscoveryResult, PreviewResult, TestResult } from '../../types'

interface SourceWizardProps {
  onClose: () => void
  onCreated?: () => void
}

type Step = 1 | 2 | 3

/**
 * 失败分类的展示文案：后端 FailureCode → 分类名 + 配色。
 * 技术上根本无法解析的情况（DNS/登录墙/反爬/SPA/非网页…）各自独立成类，
 * 用户能看到"为什么不行"而不是一句笼统的访问失败。
 */
const FAILURE_META: Record<string, { label: string; cls: string }> = {
  INVALID_URL: { label: '地址无效', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
  UNSUPPORTED_SCHEME: { label: '协议不支持', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
  SSRF_BLOCKED: { label: '安全策略拦截', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
  DNS_NOT_FOUND: { label: '域名不存在', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
  CONNECTION_FAILED: { label: '无法连接', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
  TIMEOUT: { label: '连接超时', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
  TLS_ERROR: { label: '证书异常', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
  REDIRECT_LIMIT: { label: '重定向异常', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
  HTTP_NOT_FOUND: { label: '页面不存在', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
  AUTH_REQUIRED: { label: '需要登录权限', cls: 'bg-amber-50 border-amber-200 text-amber-800' },
  BLOCKED_BY_WAF: { label: '反爬人机验证', cls: 'bg-amber-50 border-amber-200 text-amber-800' },
  RATE_LIMITED: { label: '访问限流', cls: 'bg-amber-50 border-amber-200 text-amber-800' },
  SERVER_ERROR: { label: '站点故障', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
  RESPONSE_TOO_LARGE: { label: '内容过大', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
  NOT_A_WEBPAGE: { label: '非网页内容', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
  JS_RENDERED_PAGE: { label: '动态渲染页面', cls: 'bg-sky-50 border-sky-200 text-sky-800' },
  NO_LIST_STRUCTURE: { label: '不是列表页', cls: 'bg-sky-50 border-sky-200 text-sky-800' },
  FETCH_FAILED: { label: '获取失败', cls: 'bg-gray-50 border-gray-200 text-gray-700' },
}

export function SourceWizard({ onClose, onCreated }: SourceWizardProps) {
  const qc = useQueryClient()
  const [step, setStep] = useState<Step>(1)
  const [url, setUrl] = useState('')
  const [discoveryResult, setDiscoveryResult] = useState<DiscoveryResult | null>(null)
  // 可修正的选择器映射：自动发现经常偏差，用户改完直接重新预览/验证——
  // 预览、验证与最终保存永远使用同一份配置
  const [selectors, setSelectors] = useState({
    list: '', title: '', link: '', summary: '', next_page: '',
  })
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [name, setName] = useState('')
  const [keywords, setKeywords] = useState('')
  const [cronExpression, setCronExpression] = useState('0 9 * * *')
  const [error, setError] = useState('')
  // 结构化失败（后端失败分类体系）与探测透明度
  const [failure, setFailure] = useState<DiscoveryFailure | null>(null)
  const [triedUrls, setTriedUrls] = useState<string[]>([])
  // 脏数据保护：走到第 2/3 步或已输入任何内容时，退出需确认（与
  // TaskFormModal 同一标准——此前误点遮罩/Esc 会静默丢掉全部进度）
  const [confirmDiscardOpen, setConfirmDiscardOpen] = useState(false)
  const isDirty =
    step !== 1 || url.trim() !== '' || name.trim() !== '' || keywords.trim() !== ''
  const requestClose = useCallback(() => {
    if (isDirty) {
      setConfirmDiscardOpen(true)
      return
    }
    onClose()
  }, [isDirty, onClose])
  // 焦点陷阱 + Escape 经 requestClose（组件随模态打开条件挂载）
  const modalRef = useModalA11y(requestClose)

  const discoverMutation = useMutation({
    // target：可选的显式目标（"改用推荐 Feed"按钮会用推荐地址重新发现）
    mutationFn: (target?: string) => sourcesApi.discover(target ?? url),
    onSuccess: (data) => {
      // 后端会归一化输入，并可能在回退探测中改用可抓取地址（www 变体 /
      // 常见 Feed 路径 / 页面内声明的 Feed）——把最终地址回填输入框，
      // 后续预览与保存都基于它
      if (data.url) {
        setUrl(data.url)
      }
      if (data.failure) {
        setFailure(data.failure)
        setTriedUrls(data.tried_urls || [])
        setDiscoveryResult(null)
        return
      }
      setFailure(null)
      setTriedUrls([])
      if (data.errors?.length) {
        // 兜底：后端返回了 errors 但没有结构化 failure（理论上不发生）
        setError(data.errors.join('；'))
        setDiscoveryResult(null)
        return
      }
      setDiscoveryResult(data)
      // 发现结果初始化可编辑选择器；新 URL 的旧预览/验证结果一并作废
      setSelectors({
        list: data.list_selector || '',
        title: data.title_selector || '',
        link: data.link_selector || '',
        summary: data.summary_selector || '',
        next_page: data.next_page_selector || '',
      })
      // 用站点标题预填任务名称（用户已输入或站点无名时保持现状）
      if (!name && data.title) {
        setName(data.title)
      }
      // URL 变了就重新发现，旧 URL 的预览结果必须作废，
      // 否则"继续"按钮会用上一个 URL 的 preview.success 放行
      setPreviewResult(null)
      setTestResult(null)
      setStep(2)
    },
    onError: (e: unknown) => {
      // 拦截器产出的是 ApiError（非 Error 实例），用 errorMessage 提取后端具体文案
      setError(errorMessage(e, '发现失败，请检查 URL 是否正确'))
    },
  })

  const previewMutation = useMutation({
    // 预览用「人工修正后的选择器」而不是原始发现结果——用户改完映射
    // 立即能看到修正效果，且预览与最终保存的是同一份配置
    mutationFn: () => {
      const base = discoveryResult
      if (!base) throw new Error('missing discovery')
      return sourcesApi.preview(url, {
        ...base,
        list_selector: selectors.list,
        title_selector: selectors.title,
        link_selector: selectors.link,
        summary_selector: selectors.summary,
        next_page_selector: selectors.next_page,
      })
    },
    onSuccess: (data) => {
      setPreviewResult(data)
    },
    onError: (e: unknown) => {
      setError(errorMessage(e, '预览失败'))
    },
  })

  const testMutation = useMutation({
    // 语义验证与预览使用完全相同的选择器配置
    mutationFn: () =>
      sourcesApi.test(url, {
        list: selectors.list,
        title: selectors.title,
        link: selectors.link,
        summary: selectors.summary,
      }),
    onSuccess: (data) => {
      setTestResult(data)
    },
    onError: (e: unknown) => {
      setError(errorMessage(e, '验证失败'))
    },
  })

  const saveMutation = useMutation({
    mutationFn: () =>
      tasksApi.create({
        name,
        source_url: url,
        template_id: null,
        selector_list: selectors.list,
        selector_title: selectors.title,
        selector_link: selectors.link,
        selector_summary: selectors.summary || null,
        // 自动发现/人工修正出的分页选择器必须进入任务：丢弃它会让分页源永远只抓第一页
        selector_next_page: selectors.next_page || null,
        keywords: keywords ? keywords.split(/[,，]/).map((k) => k.trim()).filter(Boolean) : [],
        cron_expression: cronExpression,
        // 自定义来源默认讨论型；条目型可在任务设置里改
        content_kind: 'discussion',
        // 验证通过才启用；验证失败/未验证保存为草稿（paused），
        // 不把未验证来源标记为健康
        status: testResult?.success ? 'active' : 'paused',
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

  // 选择器人工修正后，旧预览/验证结果立即失效
  const updateSelector = (field: keyof typeof selectors, value: string) => {
    setSelectors((prev) => ({ ...prev, [field]: value }))
    setPreviewResult(null)
    setTestResult(null)
  }

  const runDiscover = (target?: string) => {
    setError('')
    setFailure(null)
    discoverMutation.mutate(target)
  }

  const handleDiscover = () => {
    if (!url) return
    runDiscover()
  }

  const handlePreview = () => {
    setError('')
    previewMutation.mutate()
  }

  const handleSave = () => {
    setError('')
    // 自动发现失败/未产出选择器时不允许保存：空 selector 过去会打到
    // 数据库 NOT NULL 约束上返回 500，现在前后端都拦（后端返回 400）
    if (!selectors.list || !selectors.title || !selectors.link) {
      setError('列表/标题/链接选择器不能为空，请返回上一步修正后重试')
      return
    }
    saveMutation.mutate()
  }

  return (
    // 遮罩点击不关闭：向导承载多步输入，误点背景会弹出丢弃确认、打断流程，
    // 退出只能走「关闭 / 取消 / Esc」这些显式路径（均经 requestClose 的未保存保护）
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50">
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
          <button onClick={requestClose} className="text-muted hover:text-secondary" aria-label="关闭">
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
          {failure && step === 1 && (
            <div
              role="alert"
              className={`mb-4 p-3 border rounded-lg ${FAILURE_META[failure.code]?.cls ?? FAILURE_META.FETCH_FAILED.cls}`}
            >
              <div className="flex items-center gap-2 mb-1">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span className="text-sm font-medium">
                  {FAILURE_META[failure.code]?.label ?? '发现失败'}
                </span>
                <code className="text-[10px] px-1.5 py-0.5 bg-white/70 rounded text-current opacity-70">
                  {failure.code}
                </code>
              </div>
              <p className="text-sm ml-6">{failure.message}</p>
              {failure.hint && (
                <p className="text-xs ml-6 mt-1.5 flex items-start gap-1.5 text-current opacity-90">
                  <Lightbulb className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  <span>{failure.hint}</span>
                </p>
              )}
              {failure.suggested_url && (
                <button
                  type="button"
                  onClick={() => {
                    setUrl(failure.suggested_url)
                    runDiscover(failure.suggested_url)
                  }}
                  disabled={discoverMutation.isPending}
                  className="mt-2 ml-6 inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 bg-white/80 border border-current/30 rounded hover:bg-white transition-colors"
                >
                  <ArrowRightLeft className="h-3.5 w-3.5" />
                  改用探测到的内容源并重新发现：
                  <span className="font-medium break-all">{failure.suggested_url}</span>
                </button>
              )}
              {triedUrls.length > 1 && (
                <details className="ml-6 mt-2 text-xs opacity-80">
                  <summary className="cursor-pointer select-none">
                    已自动尝试 {triedUrls.length} 个地址
                  </summary>
                  <ul className="mt-1 space-y-0.5 break-all">
                    {triedUrls.map((u) => (
                      <li key={u}>· {u}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}

          {error && !failure && (
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
                      type="text"
                      inputMode="url"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="example.com 或 https://example.com/feed"
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
                输入站点根、栏目页或 Feed 地址，scheme 可省略（自动按 https 尝试）；
                站点根会自动探测常见 Feed 路径与页面内声明的订阅源。
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

              {/* 选择器可修正：自动发现经常偏差，改完重新预览/验证，
                  全程使用同一份配置 */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                {(
                  [
                    { key: 'list', label: '列表选择器', required: true },
                    { key: 'title', label: '标题字段/选择器', required: true },
                    { key: 'link', label: '链接字段/选择器', required: true },
                    { key: 'summary', label: '摘要字段/选择器', required: false },
                    { key: 'next_page', label: '分页选择器（可选）', required: false },
                  ] as const
                ).map(({ key, label, required }) => (
                  <div key={key}>
                    <label
                      htmlFor={`wizard-sel-${key}`}
                      className="block text-gray-500 mb-1"
                    >
                      {label}
                      {required && <span aria-hidden="true" className="text-danger ml-1">*</span>}
                    </label>
                    <input
                      id={`wizard-sel-${key}`}
                      type="text"
                      value={selectors[key]}
                      onChange={(e) => updateSelector(key, e.target.value)}
                      spellCheck={false}
                      aria-required={required}
                      className="w-full px-3 py-1.5 border rounded-lg font-mono text-xs focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    />
                  </div>
                ))}
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
                {/* 与 TaskFormModal 同一控件：本地时间编辑、保存为 UTC Cron，
                    取代裸 select（旧"每周"预设 0 9 * * 1 按 APScheduler
                    day_of_week 0=周一 的约定实际落在周二） */}
                <SchedulePicker value={cronExpression} onChange={setCronExpression} />
              </div>

              {/* 保存前语义验证：transport/parse/semantic 三层分开呈现，
                  字段覆盖率与警告明确展示 */}
              <div className="p-3 border rounded-lg bg-gray-50">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-gray-700">配置验证</span>
                  <button
                    type="button"
                    onClick={() => {
                      setError('')
                      testMutation.mutate()
                    }}
                    disabled={
                      testMutation.isPending ||
                      !selectors.list || !selectors.title || !selectors.link
                    }
                    className="btn-ghost px-3 py-1.5 border border-gray-300 rounded-lg text-sm hover:bg-gray-100 flex items-center gap-1.5 disabled:opacity-50"
                  >
                    {testMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Search className="h-4 w-4" />
                    )}
                    验证配置
                  </button>
                </div>

                {testResult && (
                  <div className="mt-3 space-y-1.5 text-sm" aria-live="polite">
                    <div className="flex flex-wrap gap-2">
                      <span className="text-gray-500">HTTP {testResult.http_status}</span>
                      <span className={testResult.transport_success ? 'text-green-700' : 'text-danger'}>
                        传输 {testResult.transport_success ? '✓' : '✗'}
                      </span>
                      <span className={testResult.parse_success ? 'text-green-700' : 'text-danger'}>
                        解析 {testResult.parse_success ? '✓' : '✗'}
                      </span>
                      <span className={testResult.semantic_success ? 'text-green-700' : 'text-danger'}>
                        语义 {testResult.semantic_success ? '✓' : '✗'}
                      </span>
                      <span className="text-gray-500">
                        提取 {testResult.items_found} 条 · 字段覆盖 {(testResult.field_coverage * 100).toFixed(0)}%
                      </span>
                    </div>
                    {testResult.errors.length > 0 && (
                      <ul className="text-xs text-danger list-disc list-inside">
                        {testResult.errors.map((e, i) => <li key={i}>{e}</li>)}
                      </ul>
                    )}
                    {testResult.warnings.length > 0 && (
                      <ul className="text-xs text-amber-700 list-disc list-inside">
                        {testResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
                      </ul>
                    )}
                    <p className="text-xs text-gray-500">
                      {testResult.success
                        ? '验证通过，保存后将立即启用。'
                        : '验证未通过：仍可保存为草稿（不会启用定时抓取），修正选择器后可再次验证。'}
                    </p>
                  </div>
                )}
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
                  {/* 验证未通过/未验证 → 草稿（paused），不冒充健康来源 */}
                  {testResult?.success ? '保存并启用' : '保存为草稿'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {confirmDiscardOpen && (
        <ConfirmDialog
          title="放弃未完成的配置？"
          message="向导中已填写的 URL、选择器与频率尚未保存，关闭后将全部丢失。"
          confirmText="放弃配置"
          variant="default"
          onConfirm={() => {
            setConfirmDiscardOpen(false)
            onClose()
          }}
          onCancel={() => setConfirmDiscardOpen(false)}
        />
      )}
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
