/**
 * LLMSetupCard：AI 接入配置卡片。
 *
 * 像 AI 开放平台的密钥接入页一样：服务商预设 + API Key + 拉取模型列表点选 +
 * 连通性测试，保存进后端数据库后立即生效（无需改 .env、无需重启）。
 * 支持 OpenAI 兼容与 Anthropic 两种 API 协议。
 * 密钥只写不读——页面仅展示后端返回的脱敏掩码。
 *
 * 结构：外层查询状态；表单以"已保存配置签名"为 key 重挂载——保存/清除后
 * 字段自动回到新生效值，而普通重取（数据不变）不会打断输入。
 * 字段带脏标记：只提交用户实际改动的字段，避免把预填值写成无意义覆盖。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Eye,
  EyeOff,
  ListCollapse,
  RefreshCw,
  XCircle,
} from 'lucide-react'
import { useState } from 'react'
import { toast } from 'react-hot-toast'
import { clsx } from 'clsx'
import { llmApi } from '../../api/llm'
import { errorMessage } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import { Badge } from '../ui/Badge'
import { ConfirmDialog } from '../ui/ConfirmDialog'
import { SkeletonList } from '../ui/Skeleton'
import { formatDistanceToNow } from '../../utils/time'
import type {
  LLMConfigPayload,
  LLMConfigStatus,
  LLMProtocol,
  LLMReceipt,
  LLMReceiptsOverview,
  LLMTestResult,
} from '../../types'

/** 服务商预设：一键填充协议、接口地址与常用模型（常用在前） */
const PRESETS: Array<{ label: string; protocol: LLMProtocol; baseUrl: string; model: string }> = [
  { label: 'DeepSeek', protocol: 'openai', baseUrl: 'https://api.deepseek.com', model: 'deepseek-chat' },
  { label: 'Kimi', protocol: 'openai', baseUrl: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  { label: '智谱', protocol: 'openai', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
  { label: 'OpenAI', protocol: 'openai', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { label: 'OpenRouter', protocol: 'openai', baseUrl: 'https://openrouter.ai/api/v1', model: '' },
  { label: 'LongCat', protocol: 'openai', baseUrl: 'https://api.longcat.chat/openai', model: 'LongCat-2.0' },
]

const PROTOCOL_OPTIONS: Array<{ value: LLMProtocol; label: string; hint: string }> = [
  { value: 'openai', label: 'OpenAI 兼容', hint: 'DeepSeek、Kimi、智谱、OpenAI、LongCat 等大多数服务商' },
  { value: 'anthropic', label: 'Anthropic 兼容', hint: 'Anthropic 及提供 Claude API 格式的服务商' },
]

const PURPOSE_LABELS: Record<string, string> = {
  thread_digest: '热点综述',
}

const RECEIPTS_PAGE_SIZE = 10

function formatTokens(n: number): string {
  return n.toLocaleString('en-US')
}

function purposeLabel(purpose: string): string {
  return PURPOSE_LABELS[purpose] ?? purpose
}

function savedSignature(status: LLMConfigStatus): string {
  return [status.base_url, status.model, status.api_protocol, status.usage.budget, ...status.overrides].join('|')
}

export function LLMSetupCard() {
  const { data: status, isLoading } = useQuery({
    queryKey: queryKeys.llm.config(),
    queryFn: llmApi.getConfig,
  })

  if (isLoading || !status) {
    return <SkeletonList count={1} />
  }

  return (
    <section>
      <h2 className="text-lg font-semibold mb-1">AI 接入</h2>
      <p className="text-xs text-gray-500 mb-3">
        配置一个 AI 服务的 API Key。接入后，热点会自动生成 AI 综述。
      </p>
      {/* 已保存配置变化（保存/清除）时重挂载表单，字段回到新生效值 */}
      <LLMSetupForm key={savedSignature(status)} status={status} />
    </section>
  )
}

function LLMSetupForm({ status }: { status: LLMConfigStatus }) {
  const qc = useQueryClient()
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState(status.base_url)
  const [model, setModel] = useState(status.model)
  const [protocol, setProtocol] = useState<LLMProtocol>(status.api_protocol)
  const [budget, setBudget] = useState(String(status.usage.budget))
  const [models, setModels] = useState<string[]>([])
  // 脏标记：保存时只提交用户实际改动过的字段（未动的发 null = 后端"不改动"）
  const [dirty, setDirty] = useState({
    api_key: false, base_url: false, model: false, protocol: false, budget: false,
  })
  const [showKey, setShowKey] = useState(false)
  const [testResult, setTestResult] = useState<LLMTestResult | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)
  const [showUsage, setShowUsage] = useState(false)
  const [page, setPage] = useState(1)

  const invalidate = () => qc.invalidateQueries({ queryKey: queryKeys.llm.config() })
  const markDirty = (field: keyof typeof dirty) =>
    setDirty((d) => (d[field] ? d : { ...d, [field]: true }))

  const buildPayload = (): LLMConfigPayload => ({
    api_key: dirty.api_key ? apiKey.trim() : null,
    base_url: dirty.base_url ? baseUrl.trim() : null,
    model: dirty.model ? model.trim() : null,
    api_protocol: dirty.protocol ? protocol : null,
    daily_token_budget:
      dirty.budget && budget.trim() !== '' && Number.isFinite(Number(budget.trim()))
        ? Number(budget.trim())
        : null,
  })

  const saveMutation = useMutation({
    mutationFn: () => llmApi.saveConfig(buildPayload()),
    onSuccess: (data) => {
      invalidate()
      setTestResult(null)
      toast.success(data.configured ? '已保存，AI 功能已启用' : '已保存')
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '保存失败')),
  })

  const testMutation = useMutation({
    mutationFn: () => llmApi.testConfig(buildPayload()),
    onSuccess: (result) => setTestResult(result),
    onError: (e: unknown) =>
      setTestResult({ ok: false, message: errorMessage(e, '测试失败'), model: null, latency_ms: null }),
  })

  const modelsMutation = useMutation({
    mutationFn: () => llmApi.getModels(buildPayload()),
    onSuccess: (result) => {
      setModels(result.models)
      if (!result.ok) {
        toast.error(result.message)
      } else if (result.models.length === 0) {
        toast(result.message)
      }
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '获取模型列表失败')),
  })

  const clearMutation = useMutation({
    mutationFn: () => llmApi.clearConfig(),
    onSuccess: () => {
      invalidate()
      setTestResult(null)
      setModels([])
      toast.success('已清除界面配置')
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '清除失败')),
  })

  const handlePreset = (preset: (typeof PRESETS)[number]) => {
    setProtocol(preset.protocol)
    if (protocol !== preset.protocol) markDirty('protocol')
    setBaseUrl(preset.baseUrl)
    markDirty('base_url')
    if (preset.model) {
      setModel(preset.model)
      markDirty('model')
    }
    setModels([])
  }

  // 调用记录（懒加载：展开才请求，按页取）
  const receiptsQuery = useQuery({
    queryKey: queryKeys.llm.receipts(page),
    queryFn: () => llmApi.getReceipts(RECEIPTS_PAGE_SIZE, (page - 1) * RECEIPTS_PAGE_SIZE),
    enabled: showUsage,
    staleTime: 30_000,
  })
  const total = receiptsQuery.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / RECEIPTS_PAGE_SIZE))

  const { configured, source, overrides, usage } = status
  const hasKeyOverride = overrides.includes('llm_api_key')

  let sourceNote: string
  if (overrides.length > 0) {
    sourceNote = '使用界面保存的配置'
  } else if (source === 'env') {
    sourceNote = '使用环境变量中的密钥'
  } else {
    sourceNote = '尚未配置'
  }

  const keyPlaceholder = hasKeyOverride
    ? `已保存（${status.api_key_masked}），输入新值可替换`
    : status.env_key_present
      ? '使用环境变量中的密钥，可输入以覆盖'
      : 'sk-…'

  return (
    <div className="card p-4 space-y-4">
      {/* 状态行 */}
      <div className="flex items-center gap-2 flex-wrap">
        <Badge color={configured ? 'green' : 'gray'}>{configured ? '已接入' : '未接入'}</Badge>
        {configured && usage.breaker_open && (
          <Badge color="yellow">已熔断（连续失败 {usage.consecutive_failures} 次）</Badge>
        )}
        <span className="text-xs text-gray-500">{sourceNote}</span>
        {configured && (
          <span className="text-xs text-gray-400 ml-auto">
            今日已用 {formatTokens(usage.used_today)} / {formatTokens(usage.budget)} tokens
            {usage.remaining === 0 && <span className="text-warning">，预算已用完，次日自动恢复</span>}
          </span>
        )}
      </div>

      {/* 服务商预设 */}
      <div>
        <div className="text-xs text-gray-500 mb-1.5">常用服务商</div>
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => handlePreset(p)}
              className="btn-ghost btn-sm border border-gray-200"
              aria-label={`填入 ${p.label} 的接口地址与模型`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* 接口协议 */}
      <div>
        <div className="text-xs text-gray-500 mb-1.5">接口协议</div>
        <div className="inline-flex rounded-md border border-gray-200 p-0.5">
          {PROTOCOL_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              aria-pressed={protocol === opt.value}
              title={opt.hint}
              onClick={() => { setProtocol(opt.value); markDirty('protocol') }}
              className={clsx(
                'px-3 py-1 text-xs rounded-md transition-colors',
                protocol === opt.value
                  ? 'bg-primary-600 text-white font-medium'
                  : 'text-gray-600 hover:bg-gray-100',
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* 表单 */}
      <div className="space-y-3">
        <div>
          <label htmlFor="llm-api-key" className="block text-xs text-gray-500 mb-1">
            API Key
          </label>
          <div className="relative">
            <input
              id="llm-api-key"
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => { setApiKey(e.target.value); markDirty('api_key') }}
              placeholder={keyPlaceholder}
              autoComplete="off"
              spellCheck={false}
              className="input pr-10 font-mono"
            />
            <button
              type="button"
              onClick={() => setShowKey((v) => !v)}
              aria-label={showKey ? '隐藏密钥' : '显示密钥'}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600"
            >
              {showKey
                ? <EyeOff className="h-4 w-4" aria-hidden="true" />
                : <Eye className="h-4 w-4" aria-hidden="true" />}
            </button>
          </div>
        </div>

        <div>
          <label htmlFor="llm-base-url" className="block text-xs text-gray-500 mb-1">
            接口地址
          </label>
          <input
            id="llm-base-url"
            type="text"
            value={baseUrl}
            onChange={(e) => { setBaseUrl(e.target.value); markDirty('base_url') }}
            placeholder="https://api.deepseek.com"
            autoComplete="off"
            spellCheck={false}
            className="input font-mono"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label htmlFor="llm-model" className="text-xs text-gray-500">
              模型名称
            </label>
            <button
              type="button"
              onClick={() => modelsMutation.mutate()}
              disabled={modelsMutation.isPending}
              className="inline-flex items-center gap-1 text-xs text-primary-600 hover:underline disabled:opacity-50"
            >
              <ListCollapse className="h-3 w-3" aria-hidden="true" />
              {modelsMutation.isPending ? '获取中…' : '获取模型列表'}
            </button>
          </div>
          <input
            id="llm-model"
            type="text"
            value={model}
            onChange={(e) => { setModel(e.target.value); markDirty('model') }}
            placeholder="例如 deepseek-chat"
            autoComplete="off"
            spellCheck={false}
            className="input font-mono"
          />
          {models.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
              {models.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => { setModel(m); markDirty('model') }}
                  aria-pressed={m === model}
                  className={clsx(
                    'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-mono transition-colors',
                    m === model
                      ? 'bg-primary-600 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
                  )}
                >
                  {m}
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <label htmlFor="llm-budget" className="block text-xs text-gray-500 mb-1">
            每日 token 预算
          </label>
          <input
            id="llm-budget"
            type="number"
            min={1000}
            step={1000}
            value={budget}
            onChange={(e) => { setBudget(e.target.value); markDirty('budget') }}
            className="input font-mono"
          />
          <p className="text-xs text-gray-400 mt-1">
            当日（UTC）累计消耗超过该值即暂停调用，次日自动恢复。
          </p>
        </div>
      </div>

      {/* 测试结果 */}
      {testResult && (
        <div
          role="status"
          className={`text-xs flex items-start gap-1.5 ${testResult.ok ? 'text-success' : 'text-danger'}`}
        >
          {testResult.ok
            ? <CheckCircle2 className="h-3.5 w-3.5 mt-px shrink-0" aria-hidden="true" />
            : <XCircle className="h-3.5 w-3.5 mt-px shrink-0" aria-hidden="true" />}
          <span>
            {testResult.message}
            {testResult.ok && testResult.latency_ms != null && ` · ${testResult.latency_ms}ms`}
          </span>
        </div>
      )}

      {/* 操作 */}
      <div className="flex items-center gap-2 flex-wrap pt-1">
        <button
          type="button"
          className="btn-ghost border border-gray-200"
          onClick={() => { setTestResult(null); testMutation.mutate() }}
          disabled={testMutation.isPending || saveMutation.isPending}
        >
          {testMutation.isPending ? '测试中…' : '测试连接'}
        </button>
        <button
          type="button"
          className="btn-primary"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending || testMutation.isPending}
        >
          {saveMutation.isPending ? '保存中…' : '保存'}
        </button>
        {overrides.length > 0 && (
          <button
            type="button"
            className="btn-ghost text-danger ml-auto"
            onClick={() => setConfirmClear(true)}
            disabled={clearMutation.isPending}
          >
            清除配置
          </button>
        )}
      </div>

      <p className="text-xs text-gray-400">
        密钥保存在本机数据库，仅服务端调用使用。保存后立即生效，无需重启。
      </p>

      {/* 调用记录 */}
      <div className="border-t border-gray-100 pt-3">
        <button
          type="button"
          onClick={() => setShowUsage((v) => !v)}
          aria-expanded={showUsage}
          className="flex items-center gap-1 text-sm font-semibold text-gray-700 hover:text-gray-900"
        >
          {showUsage
            ? <ChevronDown className="h-4 w-4" aria-hidden="true" />
            : <ChevronRight className="h-4 w-4" aria-hidden="true" />}
          调用记录
        </button>

        {showUsage && (
          <div className="mt-2 space-y-2">
            {receiptsQuery.isLoading ? (
              <p className="text-xs text-gray-400">加载中…</p>
            ) : receiptsQuery.isError ? (
              <p className="text-xs text-danger">
                加载失败
                <button type="button" onClick={() => receiptsQuery.refetch()} className="ml-2 text-primary-600 hover:underline">
                  重试
                </button>
              </p>
            ) : receiptsQuery.data ? (
              <>
                <UsageSummary summary={receiptsQuery.data.today} onRefresh={() => receiptsQuery.refetch()} />
                {receiptsQuery.data.receipts.length === 0 ? (
                  <p className="text-xs text-gray-400">还没有调用记录。接入后生成热点综述时会记录在这里。</p>
                ) : (
                  <div className="divide-y divide-gray-100">
                    {receiptsQuery.data.receipts.map((r) => <ReceiptRow key={r.id} receipt={r} />)}
                  </div>
                )}
                <div className="flex items-center gap-2 pt-1 text-xs text-gray-500">
                  <span>第 {page} / {totalPages} 页 · 共 {formatTokens(total)} 条</span>
                  <div className="ml-auto flex gap-1.5">
                    <button
                      type="button"
                      className="btn-ghost btn-sm border border-gray-200"
                      disabled={page <= 1 || receiptsQuery.isFetching}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      aria-label="上一页"
                    >
                      <ChevronLeft className="h-3 w-3" aria-hidden="true" />
                      上一页
                    </button>
                    <button
                      type="button"
                      className="btn-ghost btn-sm border border-gray-200"
                      disabled={page >= totalPages || receiptsQuery.isFetching}
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      aria-label="下一页"
                    >
                      下一页
                      <ChevronRight className="h-3 w-3" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        )}
      </div>

      {confirmClear && (
        <ConfirmDialog
          title="清除 AI 配置"
          message="将删除在界面保存的接入配置，回落到环境变量设置（若有）。确定清除？"
          confirmText="清除"
          variant="danger"
          onConfirm={() => {
            setConfirmClear(false)
            clearMutation.mutate()
          }}
          onCancel={() => setConfirmClear(false)}
        />
      )}
    </div>
  )
}

/** 当日调用汇总行 */
function UsageSummary({ summary, onRefresh }: { summary: LLMReceiptsOverview['today']; onRefresh: () => void }) {
  return (
    <div className="flex items-center gap-2 flex-wrap text-xs text-gray-500">
      <span className="badge badge-gray">今日 {summary.calls} 次调用</span>
      {summary.failed > 0 && <span className="badge badge-red">{summary.failed} 次失败</span>}
      <span className="badge badge-gray">{formatTokens(summary.tokens)} tokens</span>
      <button
        type="button"
        onClick={onRefresh}
        className="btn-ghost btn-sm ml-auto"
        aria-label="刷新调用记录"
      >
        <RefreshCw className="h-3 w-3" aria-hidden="true" />
      </button>
    </div>
  )
}

function ReceiptRow({ receipt: r }: { receipt: LLMReceipt }) {
  const tokens = (r.input_tokens ?? 0) + (r.output_tokens ?? 0)
  return (
    <div className="flex items-start gap-2 py-1.5">
      {r.status === 'done' ? (
        <CheckCircle2 className="h-3.5 w-3.5 mt-0.5 text-success shrink-0" aria-hidden="true" />
      ) : r.status === 'failed' ? (
        <XCircle className="h-3.5 w-3.5 mt-0.5 text-danger shrink-0" aria-hidden="true" />
      ) : (
        <Clock className="h-3.5 w-3.5 mt-0.5 text-gray-400 shrink-0" aria-hidden="true" />
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-xs">
          <span className="font-medium text-gray-700">{purposeLabel(r.purpose)}</span>
          <span className="text-gray-400 truncate" title={r.model}>{r.model}</span>
        </div>
        {r.status === 'failed' && r.error && (
          <div className="text-xs text-danger truncate mt-0.5" title={r.error}>{r.error}</div>
        )}
      </div>
      <div className="text-xs text-gray-400 shrink-0 text-right">
        {r.status === 'done' && `${formatTokens(tokens)} tok`}
        {r.status === 'done' && r.duration_ms != null && ` · ${r.duration_ms}ms`}
        <div>{formatDistanceToNow(r.created_at)}</div>
      </div>
    </div>
  )
}
