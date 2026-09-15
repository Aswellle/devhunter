import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Globe, Search, Eye, Check, Loader2, AlertCircle } from 'lucide-react'
import { sourcesApi } from '../../api/sources'
import { tasksApi } from '../../api/tasks'

interface SourceWizardProps {
  onClose: () => void
  onCreated?: () => void
}

type Step = 1 | 2 | 3

export function SourceWizard({ onClose, onCreated }: SourceWizardProps) {
  const [step, setStep] = useState<Step>(1)
  const [url, setUrl] = useState('')
  const [discoveryResult, setDiscoveryResult] = useState<any>(null)
  const [previewResult, setPreviewResult] = useState<any>(null)
  const [name, setName] = useState('')
  const [keywords, setKeywords] = useState('')
  const [cronExpression, setCronExpression] = useState('0 9 * * *')
  const [error, setError] = useState('')

  // Step 1: 发现
  const discoverMutation = useMutation({
    mutationFn: (url: string) => sourcesApi.discover(url),
    onSuccess: (data) => {
      setDiscoveryResult(data)
      setStep(2)
      setError('')
    },
    onError: (err: any) => {
      setError(err.message || 'Discovery failed')
    },
  })

  // Step 2: 预览
  const previewMutation = useMutation({
    mutationFn: () => sourcesApi.preview(url, discoveryResult),
    onSuccess: (data) => {
      setPreviewResult(data)
      setError('')
    },
    onError: (err: any) => {
      setError(err.message || 'Preview failed')
    },
  })

  // Step 3: 保存
  const saveMutation = useMutation({
    mutationFn: () => tasksApi.create({
      name: name || discoveryResult?.title || 'New Source',
      source_url: url,
      selector_list: discoveryResult?.list_selector || '',
      selector_title: discoveryResult?.title_selector || '',
      selector_link: discoveryResult?.link_selector || '',
      selector_summary: discoveryResult?.summary_selector || '',
      keywords: keywords ? keywords.split(',').map(k => k.trim()) : [],
      cron_expression: cronExpression,
    }),
    onSuccess: () => {
      onCreated?.()
      onClose()
    },
    onError: (err: any) => {
      setError(err.message || 'Save failed')
    },
  })

  const handleDiscover = () => {
    if (!url) return
    setError('')
    discoverMutation.mutate(url)
  }

  const handlePreview = () => {
    setError('')
    previewMutation.mutate()
  }

  const handleSave = () => {
    setError('')
    saveMutation.mutate()
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-lg font-semibold">Add New Source</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            ✕
          </button>
        </div>

        {/* Progress */}
        <div className="px-6 py-3 bg-gray-50 border-b">
          <div className="flex items-center gap-2">
            <StepIndicator step={1} current={step} label="URL" />
            <div className="flex-1 h-px bg-gray-300" />
            <StepIndicator step={2} current={step} label="Discover" />
            <div className="flex-1 h-px bg-gray-300" />
            <StepIndicator step={3} current={step} label="Save" />
          </div>
        </div>

        {/* Content */}
        <div className="px-6 py-4">
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700">
              <AlertCircle className="h-4 w-4" />
              <span className="text-sm">{error}</span>
            </div>
          )}

          {/* Step 1: URL Input */}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Website URL
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
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    {discoverMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Search className="h-4 w-4" />
                    )}
                    Discover
                  </button>
                </div>
              </div>
              <p className="text-sm text-gray-500">
                Enter a website URL to automatically detect its content structure.
              </p>
            </div>
          )}

          {/* Step 2: Discovery Result */}
          {step === 2 && discoveryResult && (
            <div className="space-y-4">
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <Globe className="h-4 w-4 text-blue-600" />
                  <span className="font-medium text-blue-900">
                    {discoveryResult.source_type.toUpperCase()} Detected
                  </span>
                </div>
                {discoveryResult.title && (
                  <p className="text-sm text-blue-800">{discoveryResult.title}</p>
                )}
                {discoveryResult.description && (
                  <p className="text-sm text-blue-700 mt-1">{discoveryResult.description}</p>
                )}
              </div>

              {/* Selectors */}
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-gray-500">List:</span>
                  <code className="ml-2 px-2 py-0.5 bg-gray-100 rounded text-xs">
                    {discoveryResult.list_selector || 'N/A'}
                  </code>
                </div>
                <div>
                  <span className="text-gray-500">Title:</span>
                  <code className="ml-2 px-2 py-0.5 bg-gray-100 rounded text-xs">
                    {discoveryResult.title_selector || 'N/A'}
                  </code>
                </div>
                <div>
                  <span className="text-gray-500">Link:</span>
                  <code className="ml-2 px-2 py-0.5 bg-gray-100 rounded text-xs">
                    {discoveryResult.link_selector || 'N/A'}
                  </code>
                </div>
                <div>
                  <span className="text-gray-500">Summary:</span>
                  <code className="ml-2 px-2 py-0.5 bg-gray-100 rounded text-xs">
                    {discoveryResult.summary_selector || 'N/A'}
                  </code>
                </div>
              </div>

              {/* Preview */}
              <div>
                <button
                  onClick={handlePreview}
                  disabled={previewMutation.isPending}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center justify-center gap-2"
                >
                  {previewMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                  Preview Items
                </button>
              </div>

              {/* Preview Result */}
              {previewResult && (
                <div className="border rounded-lg overflow-hidden">
                  <div className="px-3 py-2 bg-gray-50 border-b text-sm font-medium">
                    Preview ({previewResult.items.length} items)
                  </div>
                  <div className="max-h-60 overflow-y-auto">
                    {previewResult.items.map((item: any, i: number) => (
                      <div key={i} className="px-3 py-2 border-b last:border-b-0 text-sm">
                        <div className="font-medium truncate">{item.title}</div>
                        <div className="text-gray-500 truncate text-xs">{item.url}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => setStep(1)}
                  className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Back
                </button>
                <button
                  onClick={() => setStep(3)}
                  disabled={!previewResult?.success}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Continue
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Save */}
          {step === 3 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={discoveryResult?.title || 'New Source'}
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Keywords (optional, comma-separated)
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
                  Update Frequency
                </label>
                <select
                  value={cronExpression}
                  onChange={(e) => setCronExpression(e.target.value)}
                  className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="*/30 * * * *">Every 30 minutes</option>
                  <option value="0 * * * *">Every hour</option>
                  <option value="0 */6 * * *">Every 6 hours</option>
                  <option value="0 9 * * *">Every day</option>
                  <option value="0 9 * * 1">Every week</option>
                </select>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => setStep(2)}
                  className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Back
                </button>
                <button
                  onClick={handleSave}
                  disabled={saveMutation.isPending}
                  className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {saveMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Check className="h-4 w-4" />
                  )}
                  Save Source
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
  const isComplete = step < current

  return (
    <div className="flex items-center gap-1">
      <div
        className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
          isComplete
            ? 'bg-green-500 text-white'
            : isActive
            ? 'bg-blue-600 text-white'
            : 'bg-gray-200 text-gray-600'
        }`}
      >
        {isComplete ? <Check className="h-3 w-3" /> : step}
      </div>
      <span className={`text-sm ${isActive ? 'text-blue-600 font-medium' : 'text-gray-500'}`}>
        {label}
      </span>
    </div>
  )
}
