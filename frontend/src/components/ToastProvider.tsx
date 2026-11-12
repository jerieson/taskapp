import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'

import { AlertIcon, CheckCircleIcon, CloseIcon } from './icons'
import { ToastContext, type ToastApi, type ToastKind } from './toast-context'

interface Toast {
  id: number
  kind: ToastKind
  message: string
}

const DURATION_MS: Record<ToastKind, number> = { success: 4000, info: 5000, error: 7000 }
const ALERT_CLASS: Record<ToastKind, string> = {
  success: 'alert-success',
  info: 'alert-info',
  error: 'alert-error',
}

export default function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id))
  }, [])

  const show = useCallback(
    (kind: ToastKind, message: string) => {
      const id = nextId.current++
      // Keep at most 3 on screen.
      setToasts((current) => [...current.slice(-2), { id, kind, message }])
      window.setTimeout(() => dismiss(id), DURATION_MS[kind])
    },
    [dismiss],
  )

  const api = useMemo<ToastApi>(
    () => ({
      success: (message) => show('success', message),
      error: (message) => show('error', message),
      info: (message) => show('info', message),
    }),
    [show],
  )

  return (
    <ToastContext value={api}>
      {children}
      <div className="toast toast-end z-50" aria-live="polite">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role={toast.kind === 'error' ? 'alert' : 'status'}
            className={`alert ${ALERT_CLASS[toast.kind]} w-80 max-w-full`}
          >
            {toast.kind === 'success' ? <CheckCircleIcon /> : <AlertIcon />}
            <span className="min-w-0 break-words whitespace-normal">{toast.message}</span>
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square"
              onClick={() => dismiss(toast.id)}
              aria-label="Dismiss"
            >
              <CloseIcon className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext>
  )
}
