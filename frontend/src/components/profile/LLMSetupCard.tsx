/**
 * LLMSetupCard：AI 接入配置卡片。
 *
 * 像 AI 开放平台的密钥接入页一样：服务商预设一键填充 + API Key + 连通性测试，
 * 保存进后端数据库后立即生效（无需改 .env、无需重启）。
 * 密钥只写不读——页面仅展示后端返回的脱敏掩码。
 *
 * 结构：外层查询状态；表单以"已保存配置签名"为 key 重挂载——保存/清除后
 * 字段自动回到新生效值，而普通重取（数据不变）不会打断输入。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Eye, EyeOff, XCircle } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'react-hot-toast'
import { llmApi } from '../../api/llm'
import { errorMessage } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import { Badge } from '../ui/Badge'
import { ConfirmDialog } from '../ui/ConfirmDialog'
import { SkeletonList } from '../ui/Skeleton'
import type { LLMConfigStatus, LLMTestResult } from '../../types'

/** OpenAI 兼容服务商预设：一键填充接口地址与常用模型 */
const PRESETS = [
  { label: 'DeepSeek', baseUrl: 'https://api.deepseek.com', model: 'deepseek-chat' },
  { label: 'Kimi', baseUrl: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  { label: '智谱', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
  { label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { label: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1', model: '' },
]

const OVERRIDE_LABELS: Record<string, string> = {
  llm_api_key: '密钥',
  llm_base_url: '接口地址',
  llm_model: '模型',
}

function formatTokens(n: number): string {
  return n.toLocaleString('en-US')
}

function savedSignature(status: LLMConfigStatus): string {
  return [status.base_url, status.model, ...status.overrides].join('|')
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
        配置一个 OpenAI 兼容服务的 API Key。接入后，热点会自动生成 AI 综述。
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
  const [showKey, setShowKey] = useState(false)
  const [testResult, setTestResult] = useState<LLMTestResult | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)

  const invalidate = () => qc.invalidateQueries({ queryKey: queryKeys.llm.config() })

  const saveMutation = useMutation({
    mutationFn: () =>
      llmApi.saveConfig({
        api_key: apiKey.trim(),
        base_url: baseUrl.trim(),
        model: model.trim(),
      }),
    onSuccess: (data) => {
      invalidate()
      setTestResult(null)
      toast.success(data.configured ? '已保存，AI 功能已启用' : '已保存')
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '保存失败')),
  })

  const testMutation = useMutation({
    mutationFn: () =>
      llmApi.testConfig({
        api_key: apiKey.trim(),
        base_url: baseUrl.trim(),
        model: model.trim(),
      }),
    onSuccess: (result) => setTestResult(result),
    onError: (e: unknown) =>
      setTestResult({ ok: false, message: errorMessage(e, '测试失败'), model: null, latency_ms: null }),
  })

  const clearMutation = useMutation({
    mutationFn: () => llmApi.clearConfig(),
    onSuccess: () => {
      invalidate()
      setTestResult(null)
      toast.success('已清除界面配置')
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '清除失败')),
  })

  const handlePreset = (presetBaseUrl: string, presetModel: string) => {
    setBaseUrl(presetBaseUrl)
    if (presetModel) setModel(presetModel)
  }

  const { configured, source, overrides, usage } = status
  const hasKeyOverride = overrides.includes('llm_api_key')

  let sourceNote: string
  if (overrides.length > 0) {
    sourceNote = `界面配置：${overrides.map((k) => OVERRIDE_LABELS[k] ?? k).join('、')}`
  } else if (source === 'env') {
    sourceNote = '来自环境变量，在下方保存后会覆盖它'
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
              onClick={() => handlePreset(p.baseUrl, p.model)}
              className="btn-ghost btn-sm border border-gray-200"
              aria-label={`填入 ${p.label} 的接口地址与模型`}
            >
              {p.label}
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
              onChange={(e) => setApiKey(e.target.value)}
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
            接口地址（Base URL）
          </label>
          <input
            id="llm-base-url"
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.deepseek.com"
            autoComplete="off"
            spellCheck={false}
            className="input font-mono"
          />
        </div>

        <div>
          <label htmlFor="llm-model" className="block text-xs text-gray-500 mb-1">
            模型名称
          </label>
          <input
            id="llm-model"
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="例如 deepseek-chat"
            autoComplete="off"
            spellCheck={false}
            className="input font-mono"
          />
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
