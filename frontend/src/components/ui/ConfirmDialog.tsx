/**
 * ConfirmDialog：通用确认对话框。
 *
 * 用于需要用户确认的操作（如退出登录、删除等）。
 * 提供 fallback 机制：如果浏览器不支持 showModal，则使用普通 div 模拟。
 */
import { useEffect, useRef } from 'react'

interface ConfirmDialogProps {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  variant?: 'danger' | 'default'
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  title,
  message,
  confirmText = '确认',
  cancelText = '取消',
  variant = 'default',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    // Try native dialog first, fallback to manual modal
    if (typeof dialog.showModal === 'function') {
      dialog.showModal()
    } else {
      // Fallback: show as regular positioned div
      dialog.setAttribute('open', '')
      dialog.classList.add('dialog-fallback')
    }

    return () => {
      if (typeof dialog.close === 'function') {
        dialog.close()
      }
    }
  }, [])

  const handleCancel = () => {
    onCancel()
  }

  const handleConfirm = () => {
    onConfirm()
  }

  const confirmClass = variant === 'danger'
    ? 'bg-danger hover:bg-danger/90 text-sidebar-text-active'
    : 'btn-primary'

  return (
    <dialog
      ref={dialogRef}
      onClose={handleCancel}
      className="fixed inset-0 z-[300] m-auto p-0 rounded-lg shadow-2xl border-0 backdrop:bg-black/50 dialog-fallback"
    >
      <div className="w-full max-w-sm bg-surface rounded-lg shadow-xl">
        <div className="px-6 py-4 border-b border-subtle">
          <h3 className="text-base font-semibold text-primary">{title}</h3>
        </div>
        <div className="px-6 py-4">
          <p className="text-sm text-secondary">{message}</p>
        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-subtle bg-hover rounded-b-lg">
          <button onClick={handleCancel} className="btn-ghost">
            {cancelText}
          </button>
          <button onClick={handleConfirm} className={confirmClass}>
            {confirmText}
          </button>
        </div>
      </div>
    </dialog>
  )
}
