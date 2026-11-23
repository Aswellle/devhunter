/**
 * FolderDialog：新建 / 重命名收藏文件夹。
 *
 * 与 PreferenceModal 同一模态规范：遮罩不关闭、Esc 取消、焦点陷阱、
 * 提交只走表单（Enter 可直接保存）。
 */
import { useId, useState } from 'react'
import { useModalA11y } from '../../hooks/useModalA11y'

interface FolderDialogProps {
  title: string
  initialName?: string
  confirmText: string
  pending?: boolean
  error?: string | null
  onCancel: () => void
  onSubmit: (name: string) => void
}

export function FolderDialog({
  title,
  initialName = '',
  confirmText,
  pending = false,
  error = null,
  onCancel,
  onSubmit,
}: FolderDialogProps) {
  const [name, setName] = useState(initialName)
  const [localError, setLocalError] = useState<string | null>(null)
  const titleId = useId()
  const inputId = useId()
  const modalRef = useModalA11y(onCancel)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const normalized = name.trim().replace(/\s+/g, ' ')
    if (!normalized) {
      setLocalError('请输入文件夹名称')
      return
    }
    if (normalized.length > 40) {
      setLocalError('文件夹名称不能超过 40 个字符')
      return
    }
    setLocalError(null)
    onSubmit(normalized)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative w-full max-w-sm mx-4 bg-white rounded-2xl shadow-2xl overflow-hidden"
      >
        <form onSubmit={handleSubmit}>
          <div className="px-5 py-4 border-b border-gray-100">
            <h3 id={titleId} className="text-base font-semibold text-gray-900">
              {title}
            </h3>
          </div>
          <div className="px-5 py-4">
            <label htmlFor={inputId} className="block text-xs font-medium text-gray-600 mb-1">
              文件夹名称
            </label>
            <input
              id={inputId}
              className="input"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (localError) setLocalError(null)
              }}
              maxLength={40}
              autoComplete="off"
              placeholder="例如：待读长文"
              disabled={pending}
            />
            <p className="text-[11px] text-gray-400 mt-1.5">
              最多 40 个字符；名称不可与已有文件夹重复。
            </p>
            {(localError || error) && (
              <p role="alert" className="text-xs text-red-600 mt-2">
                {localError || error}
              </p>
            )}
          </div>
          <div className="flex justify-end gap-2 px-5 py-3 border-t border-gray-100 bg-gray-50">
            <button type="button" onClick={onCancel} className="btn-ghost" disabled={pending}>
              取消
            </button>
            <button type="submit" className="btn-primary" disabled={pending}>
              {pending ? '保存中…' : confirmText}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
