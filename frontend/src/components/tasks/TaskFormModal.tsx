import { useCallback, useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { X } from 'lucide-react'
import { tasksApi } from '../../api/tasks'
import { queryKeys } from '../../api/queryKeys'
import { errorMessage } from '../../api/client'
import type { SourceTemplate, Task, TaskCreate } from '../../types'
import { SchedulePicker } from './SchedulePicker'
import { isValidCronExpression } from '../../utils/schedule'
import { Spinner } from '../ui/Spinner'
import { ConfirmDialog } from '../ui/ConfirmDialog'
import { useModalA11y } from '../../hooks/useModalA11y'

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
  content_kind: 'discussion',
}

/** 编辑回填：仅在挂载时用于初始化（见下方 initialForm） */
function toFormState(task: Task): TaskCreate {
  return {
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
    content_kind: task.content_kind,
  }
}

export function TaskFormModal({ task, onClose }: TaskFormModalProps) {
  const qc = useQueryClient()
  const isEdit = !!task
  const titleId = useId()

  // 初始值仅在挂载时计算一次。编辑态下任务详情在模态挂载前已就绪
  // （TasksPage 等待详情 fetch 完成才渲染本组件），之后的 refetch 不会
  // 回灌表单、不会覆盖用户未保存的修改（旧实现用 useEffect 随 task 引用变化整表回填）
  const [initialForm] = useState<TaskCreate>(() => (task ? toFormState(task) : EMPTY_FORM))
  const [initialKeywords] = useState(() => (task?.keywords ?? []).join(', '))
  const [form, setForm] = useState<TaskCreate>(initialForm)
  const [keywordsInput, setKeywordsInput] = useState(initialKeywords)
  const [selectedCategory, setSelectedCategory] = useState<string>('')
  const [confirmDiscardOpen, setConfirmDiscardOpen] = useState(false)

  const { data: templates } = useQuery({
    queryKey: queryKeys.tasks.templates(),
    queryFn: tasksApi.templates,
  })

  // Extract unique categories from templates
  const categories = templates
    ? [...new Set(templates.map((t) => t.category).filter((c): c is string => Boolean(c)))]
    : []
  const filteredTemplates = templates
    ? selectedCategory
      ? templates.filter((t) => t.category === selectedCategory)
      : templates
    : []

  const isDirty =
    form.name !== initialForm.name ||
    form.source_url !== initialForm.source_url ||
    form.template_id !== initialForm.template_id ||
    form.selector_list !== initialForm.selector_list ||
    form.selector_title !== initialForm.selector_title ||
    form.selector_link !== initialForm.selector_link ||
    (form.selector_summary ?? '') !== (initialForm.selector_summary ?? '') ||
    (form.selector_next_page ?? '') !== (initialForm.selector_next_page ?? '') ||
    form.cron_expression !== initialForm.cron_expression ||
    form.content_kind !== initialForm.content_kind ||
    keywordsInput !== initialKeywords

  // requestClose 的身份会随 isDirty 变化，但 useModalA11y 内部用 ref 持有回调，
  // 不会因此重跑 a11y effect、也就不会把焦点抢回第一个输入框
  const requestClose = useCallback(() => {
    if (isDirty) {
      setConfirmDiscardOpen(true)
      return
    }
    onClose()
  }, [isDirty, onClose])

  const modalRef = useModalA11y(requestClose)

  const cronInvalid = !isValidCronExpression(form.cron_expression)

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
      content_kind: tpl.content_kind,
    }))
  }

  const mutation = useMutation({
    mutationFn: (data: TaskCreate) =>
      isEdit
        ? tasksApi.update(task!.id, data)
        : tasksApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.tasks.all })
      toast.success(isEdit ? '任务已更新' : '任务创建成功')
      onClose()
    },
    onError: (e: unknown) => {
      // client.ts 拦截器已把后端 {"error":{code,message}} 解包成 ApiError
      toast.error(errorMessage(e, '操作失败'))
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const kws = keywordsInput
      .split(/[,，]/)
      .map((k) => k.trim())
      .filter(Boolean)
    // Optional selector fields are typed str | None in the schema. An empty
    // string fails the backend's CSS-selector validator with a 422, so coerce
    // blanks to null — "left blank" and "not set" are semantically identical.
    const payload: TaskCreate = {
      ...form,
      keywords: kws,
      selector_summary: form.selector_summary?.trim() || null,
      selector_next_page: form.selector_next_page?.trim() || null,
    }
    mutation.mutate(payload)
  }

  const set = <K extends keyof TaskCreate>(key: K, value: TaskCreate[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={requestClose} />

      {/* Modal */}
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
      >
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between rounded-t-xl z-10">
          <h2 id={titleId} className="text-lg font-bold text-gray-900">
            {isEdit ? '编辑采集任务' : '新建采集任务'}
          </h2>
          <button onClick={requestClose} className="btn-ghost p-1" aria-label="关闭">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-5">

          {/* 预设模板选择（新建时显示） */}
          {!isEdit && templates && templates.length > 0 && (
            <div>
              {/* Category tabs */}
              {categories.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-3">
                  <button
                    type="button"
                    onClick={() => setSelectedCategory('')}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                      !selectedCategory
                        ? 'bg-primary-100 text-primary-700'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    全部
                  </button>
                  {categories.map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => setSelectedCategory(cat)}
                      className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                        selectedCategory === cat
                          ? 'bg-primary-100 text-primary-700'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {filteredTemplates.map((tpl) => (
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
              {([
                { key: 'selector_list',    label: '列表项 Selector *',    required: true },
                { key: 'selector_title',   label: '标题 Selector *',      required: true },
                { key: 'selector_link',    label: '链接 Selector *',      required: true },
                { key: 'selector_summary', label: '摘要 Selector（可选）', required: false },
                { key: 'selector_next_page', label: '下一页 Selector（可选，分页抓取）', required: false },
              ] as const).map(({ key, label, required }) => (
                <div key={key}>
                  <label className="text-xs text-gray-600 mb-1 block">{label}</label>
                  <input
                    className="input font-mono text-xs"
                    placeholder=".class > a"
                    value={form[key] ?? ''}
                    onChange={(e) => set(key, e.target.value)}
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

          {/* 内容性质 */}
          <div>
            <label className="label">内容性质</label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2" role="radiogroup" aria-label="内容性质">
              {([
                {
                  value: 'discussion',
                  title: '讨论型',
                  desc: 'HN、V2EX 这类社区讨论，可聚合成热点',
                },
                {
                  value: 'catalog',
                  title: '条目型',
                  desc: 'GitHub Trending 这类榜单条目，不参与聚合',
                },
              ] as const).map(({ value, title, desc }) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={form.content_kind === value}
                  onClick={() => set('content_kind', value)}
                  className={`text-left p-2.5 rounded-lg border text-xs transition-colors ${
                    form.content_kind === value
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className={`font-medium ${form.content_kind === value ? 'text-primary-700' : 'text-gray-900'}`}>
                    {title}
                  </div>
                  <div className="text-gray-500 mt-0.5 leading-relaxed">{desc}</div>
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-1">
              只有讨论型来源的内容会进入「热点聚合」；选模板时会自动带入建议分类
            </p>
          </div>

          {/* 执行频率 */}
          <div>
            <label className="label">执行频率 <span className="text-red-500">*</span></label>
            <SchedulePicker
              value={form.cron_expression}
              onChange={(cron) => set('cron_expression', cron)}
            />
            {cronInvalid && (
              <p className="text-xs text-red-500 mt-1" role="alert">
                Cron 表达式无效（需要 5 段），修正后才能提交
              </p>
            )}
          </div>

          {/* Submit */}
          <div className="flex items-center justify-end gap-3 pt-2 border-t border-gray-100">
            <button type="button" className="btn-ghost" onClick={requestClose}>
              取消
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={mutation.isPending || cronInvalid}
            >
              {mutation.isPending && <Spinner className="h-4 w-4" />}
              {isEdit ? '保存修改' : '创建任务'}
            </button>
          </div>
        </form>
      </div>

      {/* 表单有未保存修改时，关闭前需要用户确认（backdrop/Escape/取消/关闭按钮共用 requestClose） */}
      {confirmDiscardOpen && (
        <ConfirmDialog
          title="放弃未保存的修改？"
          message="表单中有未保存的修改，关闭后将全部丢失。"
          confirmText="放弃修改"
          cancelText="继续编辑"
          variant="danger"
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
