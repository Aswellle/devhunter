/**
 * ConfirmDialog：通用确认对话框。
 *
 * 用于需要用户确认的操作（如退出登录、删除等）。
 * 符合 WAI-ARIA Dialog Pattern：焦点捕获、Escape 关闭、backdrop 关闭、
 * 焦点还原、ARIA 属性完整。
 */
import { useCallback, useEffect, useRef } from 'react'

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
  const triggerRef = useRef<HTMLElement | null>(null)
  const titleId = useRef(`dialog-title-${Math.random().toString(36).slice(2, 9)}`)

  // 存储触发元素，关闭时还原焦点
  useEffect(() => {
    triggerRef.current = document.activeElement as HTMLElement
    return () => {
      triggerRef.current?.focus()
    }
  }, [])

  // 焦点陷阱：将焦点限制在 dialog 内
  const trapFocus = useCallback((e: KeyboardEvent) => {
    if (e.key !== 'Tab') return
    const dialog = dialogRef.current
    if (!dialog) return

    const focusable = dialog.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
    if (focusable.length === 0) return

    const first = focusable[0]
    const last = focusable[focusable.length - 1]

    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }, [])

  // Escape 关闭 + 焦点陷阱
  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onCancel()
      }
      trapFocus(e)
    }

    dialog.addEventListener('keydown', handleKeyDown)

    // 打开时聚焦到第一个可聚焦元素
    const firstFocusable = dialog.querySelector<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled])'
    )
    firstFocusable?.focus()

    return () => {
      dialog.removeEventListener('keydown', handleKeyDown)
    }
  }, [onCancel, trapFocus])

  // backdrop 点击关闭
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === dialogRef.current) {
      onCancel()
    }
  }

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
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId.current}
      onClose={handleCancel}
      onClick={handleBackdropClick}
      className="fixed inset-0 z-[300] m-auto p-0 rounded-lg shadow-2xl border-0 backdrop:bg-black/50 bg-transparent"
    >
      <div className="w-full max-w-sm bg-surface rounded-lg shadow-xl">
        <div className="px-6 py-4 border-b border-subtle">
          <h3 id={titleId.current} className="text-base font-semibold text-primary">
            {title}
          </h3>
        </div>
        <div className="px-6 py-4">
          <p className="text-sm text-secondary">{message}</p>
        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-subtle bg-hover rounded-b-lg">
          <button
            type="button"
            onClick={handleCancel}
            className="btn-ghost"
          >
            {cancelText}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className={confirmClass}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </dialog>
  )
}
