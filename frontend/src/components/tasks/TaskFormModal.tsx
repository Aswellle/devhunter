import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { X } from 'lucide-react'
import { tasksApi } from '../../api/tasks'
import type { SourceTemplate, Task, TaskCreate } from '../../types'
import { CRON_PRESETS } from '../../types'
import { Spinner } from '../ui/Spinner'

interface TaskFormModalProps {
  task?: Task | null
  onClose: () => void
}

const EMPTY_FORM: TaskCreate = {
  name: '',
  source_url: '',
  template_id: null,
  selector_list: '',
  selector_title: '',
  selector_link: '',
  selector_summary: '',
  selector_next_page: '',
  keywords: [],
  cron_expression: '0 * * * *',
}

export function TaskFormModal({ task, onClose }: TaskFormModalProps) {
  const qc = useQueryClient()
  const isEdit = !!task

  const [form, setForm] = useState<TaskCreate>(EMPTY_FORM)
  const [keywordsInput, setKeywordsInput] = useState('')
  const [useCustomCron, setUseCustomCron] = useState(false)

  const { data: templates } = useQuery({
    queryKey: ['templates'],
    queryFn: tasksApi.templates,
  })

  // Populate form when editing
  useEffect(() => {
    if (task) {
      setForm({
        name: task.name,
        source_url: task.source_url,
        template_id: task.template_id,
        selector_list: task.selector_list,
        selector_title: task.selector_title,
        selector_link: task.selector_link,
        selector_summary: task.selector_summary ?? '',
        selector_next_page: task.selector_next_page ?? '',
        keywords: task.keywords,
        cron_expression: task.cron_expression,
      })
      setKeywordsInput((task.keywords ?? []).join(', '))
      const isPreset = CRON_PRESETS.some((p) => p.value === task.cron_expression)
      setUseCustomCron(!isPreset)
    }
  }, [task, setKeywordsInput, setUseCustomCron])

  const applyTemplate = (tpl: SourceTemplate) => {
    setForm((f) => ({
      ...f,
      template_id: tpl.id,
      source_url: tpl.source_url,
      selector_list: tpl.selector_list,
      selector_title: tpl.selector_title,
      selector_link: tpl.selector_link,
      selector_summary: tpl.selector_summary ?? '',
      cron_expression: tpl.recommended_cron,
    }))
    setUseCustomCron(false)
  }

  const mutation = useMutation({
    mutationFn: (data: TaskCreate) =>
      isEdit
        ? tasksApi.update(task!.id, data)
        : tasksApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success(isEdit ? '任务已更新' : '任务创建成功')
      onClose()
    },
    onError: (e: any) => {
      const msg =
        e?.response?.data?.error?.message ||
        e?.response?.data?.message ||
        e?.response?.data?.error ||
        e?.message ||
        '操作失败'
      toast.error(msg)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const kws = keywordsInput
      .split(/[,，]/)
      .map((k) => k.trim())
      .filter(Boolean)
    mutation.mutate({ ...form, keywords: kws })
  }

  const set = (key: keyof TaskCreate, value: any) =>
    setForm((f) => ({ ...f, [key]: value }))

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between rounded-t-xl z-10">
          <h2 className="text-lg font-bold text-gray-900">
            {isEdit ? '编辑采集任务' : '新建采集任务'}
          </h2>
          <button onClick={onClose} className="btn-ghost p-1">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-5">

          {/* 预设模板选择（新建时显示） */}
          {!isEdit && templates && templates.length > 0 && (
            <div>
              <label className="label">选择预设模板（可选）</label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {templates.map((tpl) => (
                  <button
                    key={tpl.id}
                    type="button"
                    onClick={() => applyTemplate(tpl)}
                    className={`text-left p-2.5 rounded-lg border text-xs transition-colors ${
                      form.template_id === tpl.id
                        ? 'border-primary-500 bg-primary-50 text-primary-700'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="font-medium">{tpl.name}</div>
                    <div className="text-gray-500 mt-0.5 truncate">{tpl.description}</div>
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setForm({ ...EMPTY_FORM, template_id: null })}
                  className={`text-left p-2.5 rounded-lg border text-xs transition-colors ${
                    !form.template_id
                      ? 'border-primary-500 bg-primary-50 text-primary-700'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="font-medium">自定义</div>
                  <div className="text-gray-500 mt-0.5">手动填写所有字段</div>
                </button>
              </div>
            </div>
          )}

          {/* 任务名称 */}
          <div>
            <label className="label">任务名称 <span className="text-red-500">*</span></label>
            <input
              className="input"
              placeholder="例：HN 前端需求监控"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              required
              maxLength={100}
            />
          </div>

          {/* 目标 URL */}
          <div>
            <label className="label">目标 URL <span className="text-red-500">*</span></label>
            <input
              className="input font-mono text-xs"
              placeholder="https://news.ycombinator.com/"
              value={form.source_url}
              onChange={(e) => set('source_url', e.target.value)}
              required
              type="url"
            />
          </div>

          {/* Selectors */}
          <div className="space-y-3">
            <label className="label">CSS Selector 配置</label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                { key: 'selector_list',    label: '列表项 Selector *',    required: true },
                { key: 'selector_title',   label: '标题 Selector *',      required: true },
                { key: 'selector_link',    label: '链接 Selector *',      required: true },
                { key: 'selector_summary', label: '摘要 Selector（可选）', required: false },
                { key: 'selector_next_page', label: '下一页 Selector（可选，分页抓取）', required: false },
              ].map(({ key, label, required }) => (
                <div key={key}>
                  <label className="text-xs text-gray-600 mb-1 block">{label}</label>
                  <input
                    className="input font-mono text-xs"
                    placeholder=".class > a"
                    value={(form as any)[key] ?? ''}
                    onChange={(e) => set(key as keyof TaskCreate, e.target.value)}
                    required={required}
                  />
                </div>
              ))}
            </div>
          </div>

          {/* 关键词 */}
          <div>
            <label className="label">关键词过滤（逗号分隔，留空 = 全量采集）</label>
            <input
              className="input"
              placeholder="React, Python, hiring, 求职"
              value={keywordsInput}
              onChange={(e) => setKeywordsInput(e.target.value)}
            />
            <p className="text-xs text-gray-400 mt-1">
              标题或摘要包含任意一个关键词的条目才会被保留
            </p>
          </div>

          {/* 执行频率 */}
          <div>
            <label className="label">执行频率 <span className="text-red-500">*</span></label>
            <div className="flex flex-wrap gap-2 mb-2">
              {CRON_PRESETS.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => { set('cron_expression', p.value); setUseCustomCron(false) }}
                  className={`px-3 py-1 rounded-full text-xs border transition-colors ${
                    !useCustomCron && form.cron_expression === p.value
                      ? 'bg-primary-600 text-white border-primary-600'
                      : 'border-gray-300 text-gray-600 hover:border-primary-400'
                  }`}
                >
                  {p.label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setUseCustomCron(true)}
                className={`px-3 py-1 rounded-full text-xs border transition-colors ${
                  useCustomCron
                    ? 'bg-primary-600 text-white border-primary-600'
                    : 'border-gray-300 text-gray-600 hover:border-primary-400'
                }`}
              >
                自定义 Cron
              </button>
            </div>
            {useCustomCron && (
              <input
                className="input font-mono text-sm"
                placeholder="0 */6 * * *"
                value={form.cron_expression}
                onChange={(e) => set('cron_expression', e.target.value)}
                required
              />
            )}
          </div>

          {/* Submit */}
          <div className="flex items-center justify-end gap-3 pt-2 border-t border-gray-100">
            <button type="button" className="btn-ghost" onClick={onClose}>
              取消
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={mutation.isPending}
            >
              {mutation.isPending && <Spinner className="h-4 w-4" />}
              {isEdit ? '保存修改' : '创建任务'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
