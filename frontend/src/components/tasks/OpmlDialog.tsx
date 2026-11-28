/**
 * OpmlDialog：OPML 导入 / 导出对话框（PROD-001）。
 *
 * 导入：选择 .opml/.xml 文件 → 后端预览（SSRF 校验 + 重复标记）→
 *       勾选条目 → 以草稿（paused）创建 RSS 任务，用户验证后再启用。
 * 导出：把已启用的 RSS 来源下载为 OPML（带认证 Cookie 的 fetch + blob）。
 */
import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Download, FileUp, Loader2, AlertCircle, Check } from 'lucide-react'
import { sourcesApi, type OpmlPreviewEntry } from '../../api/sources'
import { queryKeys } from '../../api/queryKeys'
import { errorMessage } from '../../api/client'
import { useModalA11y } from '../../hooks/useModalA11y'

interface OpmlDialogProps {
  onClose: () => void
}

export function OpmlDialog({ onClose }: OpmlDialogProps) {
  const qc = useQueryClient()
  const modalRef = useModalA11y(onClose)
  const fileRef = useRef<HTMLInputElement | null>(null)
  const [entries, setEntries] = useState<OpmlPreviewEntry[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [error, setError] = useState('')
  const [result, setResult] = useState<{
    created: number; skipped_duplicate: number; skipped_unsafe: number
  } | null>(null)

  const previewMutation = useMutation({
    mutationFn: (content: string) => sourcesApi.opmlPreview(content),
    onSuccess: (data) => {
      setEntries(data.entries)
      // 只预选可用且不重复的条目
      setSelected(new Set(
        data.entries.filter((e) => e.safe && !e.duplicate).map((e) => e.xml_url),
      ))
      setResult(null)
    },
    onError: (e: unknown) => setError(errorMessage(e, 'OPML 解析失败')),
  })

  const importMutation = useMutation({
    mutationFn: () => sourcesApi.opmlImport(
      entries
        .filter((e) => selected.has(e.xml_url))
        .map((e) => ({ xml_url: e.xml_url, title: e.title, html_url: e.html_url })),
    ),
    onSuccess: (data) => {
      setResult(data)
      qc.invalidateQueries({ queryKey: queryKeys.tasks.all })
    },
    onError: (e: unknown) => setError(errorMessage(e, '导入失败')),
  })

  const handleFile = async (file: File | undefined) => {
    if (!file) return
    setError('')
    if (file.size > 2 * 1024 * 1024) {
      setError('文件过大（上限 2MB）')
      return
    }
    previewMutation.mutate(await file.text())
  }

  const handleExport = async () => {
    setError('')
    try {
      const resp = await fetch('/api/sources/opml/export', { credentials: 'include' })
      if (!resp.ok) {
        setError(`导出失败（HTTP ${resp.status}）`)
        return
      }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'devhunter-feeds.opml'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setError('导出失败，请稍后重试')
    }
  }

  const toggle = (url: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(url)) next.delete(url)
      else next.add(url)
      return next
    })
  }

  const selectable = entries.filter((e) => e.safe && !e.duplicate)

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50">
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="opml-dialog-title"
        className="bg-surface rounded-lg shadow-xl w-[720px] max-w-[92vw] max-h-[85vh] flex flex-col overflow-hidden"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-subtle shrink-0">
          <h2 id="opml-dialog-title" className="text-lg font-semibold text-primary">
            OPML 导入 / 导出
          </h2>
          <button onClick={onClose} className="text-muted hover:text-secondary" aria-label="关闭">✕</button>
        </div>

        <div className="px-6 py-4 overflow-y-auto space-y-4">
          {error && (
            <div role="alert" className="p-3 bg-danger-light border border-danger/20 rounded-lg flex items-center gap-2 text-danger text-sm">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => fileRef.current?.click()}
              disabled={previewMutation.isPending}
              className="btn-ghost px-3 py-1.5 border border-gray-300 rounded-lg text-sm flex items-center gap-1.5 hover:bg-gray-50 disabled:opacity-50"
            >
              {previewMutation.isPending
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <FileUp className="h-4 w-4" />}
              选择 OPML 文件
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".opml,.xml,text/xml,application/xml"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
            <button
              onClick={handleExport}
              className="btn-ghost px-3 py-1.5 border border-gray-300 rounded-lg text-sm flex items-center gap-1.5 hover:bg-gray-50"
            >
              <Download className="h-4 w-4" />
              导出已启用的 RSS 来源
            </button>
          </div>

          {entries.length > 0 && (
            <div className="border rounded-lg overflow-hidden">
              <div className="px-3 py-2 bg-gray-50 border-b text-sm flex items-center justify-between">
                <span>
                  共 {entries.length} 条 · 可导入 {selectable.length} 条
                  {entries.length - selectable.length > 0 && (
                    <span className="text-gray-500">
                      （{entries.filter((e) => e.duplicate).length} 条重复、
                      {entries.filter((e) => !e.safe).length} 条被安全策略拦截）
                    </span>
                  )}
                </span>
              </div>
              <div className="max-h-64 overflow-y-auto">
                {entries.map((e) => {
                  const disabled = !e.safe || e.duplicate
                  return (
                    <label
                      key={e.xml_url}
                      className={`flex items-start gap-2 px-3 py-2 border-b last:border-b-0 text-sm ${disabled ? 'opacity-60' : 'cursor-pointer hover:bg-gray-50'}`}
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(e.xml_url)}
                        disabled={disabled}
                        onChange={() => toggle(e.xml_url)}
                        className="mt-1"
                      />
                      <span className="min-w-0">
                        <span className="font-medium block truncate">{e.title}</span>
                        <span className="text-xs text-gray-500 block truncate">{e.xml_url}</span>
                        {e.duplicate && <span className="text-xs text-amber-700">已存在同地址来源，跳过</span>}
                        {!e.safe && (
                          <span className="text-xs text-danger">安全策略拦截：{e.error}</span>
                        )}
                      </span>
                    </label>
                  )
                })}
              </div>
            </div>
          )}

          {result && (
            <div role="status" aria-live="polite" className="p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800">
              <p className="flex items-center gap-1.5 font-medium">
                <Check className="h-4 w-4" />
                已导入 {result.created} 条为草稿
              </p>
              <p className="mt-1 text-xs">
                草稿任务不会定时抓取；请在任务列表逐个确认配置并启用。
                {result.skipped_duplicate > 0 && ` 跳过重复 ${result.skipped_duplicate} 条。`}
                {result.skipped_unsafe > 0 && ` 跳过不安全地址 ${result.skipped_unsafe} 条。`}
              </p>
            </div>
          )}

          <p className="text-xs text-gray-500">
            导入的来源以草稿（暂停）状态保存：先验证一次抓取结果，确认字段与
            频率后再在任务列表启用，避免外部清单直接触发未验证的定时抓取。
          </p>
        </div>

        <div className="px-6 py-4 border-t border-subtle flex justify-end gap-2 shrink-0">
          <button onClick={onClose} className="btn-ghost px-4 py-2 border border-gray-300 rounded-lg">
            关闭
          </button>
          <button
            onClick={() => { setError(''); importMutation.mutate() }}
            disabled={importMutation.isPending || selected.size === 0}
            className="btn-primary px-4 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            {importMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            导入选中（{selected.size}）
          </button>
        </div>
      </div>
    </div>
  )
}
