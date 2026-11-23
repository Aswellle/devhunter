/**
 * AggregateThreadDialog：把勾选的多条内容手动聚合为一个热点 Thread。
 *
 * 自动聚类依赖标题/实体相似度，跨语种或表述差异大的同事件报道可能
 * 认不出来；这是用户侧的兜底入口。
 */
import { useId, useState } from 'react'
import { useModalA11y } from '../../hooks/useModalA11y'

interface AggregateThreadDialogProps {
  itemCount: number
  defaultTitle: string
  pending?: boolean
  error?: string | null
  onCancel: () => void
  /** 空字符串表示使用后端默认标题（最长条目标题） */
  onSubmit: (title: string) => void
}

export function AggregateThreadDialog({
  itemCount,
  defaultTitle,
  pending = false,
  error = null,
  onCancel,
  onSubmit,
}: AggregateThreadDialogProps) {
  const [title, setTitle] = useState(defaultTitle)
  const titleId = useId()
  const inputId = useId()
  const modalRef = useModalA11y(onCancel)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit(title.trim())
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative w-full max-w-md mx-4 bg-white rounded-2xl shadow-2xl overflow-hidden"
      >
        <form onSubmit={handleSubmit}>
          <div className="px-5 py-4 border-b border-gray-100">
            <h3 id={titleId} className="text-base font-semibold text-gray-900">
              聚合为热点
            </h3>
          </div>
          <div className="px-5 py-4">
            <p className="text-xs text-gray-500 leading-relaxed mb-3">
              选中的 <b className="text-gray-700">{itemCount}</b> 条内容会从各自原有热点中移出，
              组成一个新的热点 Thread。自动聚类后续仍会向它追加同类报道。
            </p>
            <label htmlFor={inputId} className="block text-xs font-medium text-gray-600 mb-1">
              热点标题
            </label>
            <input
              id={inputId}
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={300}
              autoComplete="off"
              placeholder={defaultTitle || '留空则使用最长条目的标题'}
              disabled={pending}
            />
            <p className="text-[11px] text-gray-400 mt-1.5">
              留空则自动取选中内容中最长的标题。
            </p>
            {error && (
              <p role="alert" className="text-xs text-red-600 mt-2">
                {error}
              </p>
            )}
          </div>
          <div className="flex justify-end gap-2 px-5 py-3 border-t border-gray-100 bg-gray-50">
            <button type="button" onClick={onCancel} className="btn-ghost" disabled={pending}>
              取消
            </button>
            <button type="submit" className="btn-primary" disabled={pending}>
              {pending ? '聚合中…' : '创建热点'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
