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
 * - sets aria-hidden on background content to prevent screen reader access
 *
 * `active` must reflect the modal's actual open state (e.g. the same
 * boolean used to decide whether to render the dialog markup at all).
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

    // Capture the element that had focus before the modal opened
    const previouslyFocused = document.activeElement as HTMLElement | null

    // Set aria-hidden on background content
    const mainContent = document.getElementById('main-content')
    const originalAriaHidden = mainContent?.getAttribute('aria-hidden')
    if (mainContent) {
      mainContent.setAttribute('aria-hidden', 'true')
    }

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
      // Restore aria-hidden on background content
      if (mainContent) {
        if (originalAriaHidden === null) {
          mainContent.removeAttribute('aria-hidden')
        } else if (originalAriaHidden !== undefined) {
          mainContent.setAttribute('aria-hidden', originalAriaHidden)
        }
      }
      // Restore focus to the trigger element
      if (previouslyFocused && previouslyFocused.isConnected) {
        previouslyFocused.focus()
      }
    }
  }, [onClose, active])

  return containerRef
}
