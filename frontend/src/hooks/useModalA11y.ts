import { useEffect, useRef } from 'react'

/**
 * U2: shared modal accessibility behavior — previously TaskFormModal and
 * PreferenceModal had no role="dialog"/aria-modal, no focus trap, and no
 * initial focus, so Tab after opening either modal moved focus into the
 * backdrop-covered page content instead of staying inside the dialog.
 *
 * Returns a ref to attach to the modal's outer container. While `active`
 * is true:
 * - moves focus to the first focusable element inside the container
 * - traps Tab/Shift+Tab within the container's focusable elements
 * - calls onClose on Escape
 *
 * `active` must reflect the modal's actual open state (e.g. the same
 * boolean used to decide whether to render the dialog markup at all).
 * Some modals unmount when closed (conditional render / portal), others
 * stay mounted and toggle visibility via a prop — passing `active` lets
 * this hook's effect re-run correctly in both cases; relying on mount-only
 * (`useEffect` with no `active` dependency) would silently never re-attach
 * the focus trap for a modal that stays mounted across open/close toggles.
 */
export function useModalA11y(onClose: () => void, active: boolean = true) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!active) return
    const container = containerRef.current
    if (!container) return

    const FOCUSABLE_SELECTOR =
      'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'

    const getFocusable = () =>
      Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
        (el) => el.offsetParent !== null
      )

    // U2: capture the element that had focus before the modal opened so we
    // can restore it on close — otherwise focus is left stranded on the
    // backdrop-covered page (or lost entirely), forcing keyboard users to
    // tab back through intervening content to reach their prior position.
    const previouslyFocused = document.activeElement as HTMLElement | null

    const focusable = getFocusable()
    focusable[0]?.focus()

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key !== 'Tab') return

      const items = getFocusable()
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      // U2: restore focus to the trigger element. Guard against the
      // element having been unmounted (e.g. list item removed while modal
      // was open) — only call focus() if it's still attached to the DOM.
      if (previouslyFocused && previouslyFocused.isConnected) {
        previouslyFocused.focus()
      }
    }
  }, [onClose, active])

  return containerRef
}
