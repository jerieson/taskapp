import { errorMessage } from '../api/client'
import { AlertIcon } from './icons'

interface ErrorAlertProps {
  error: unknown
  /** Shows a "Try again" button (e.g. a query's refetch). */
  onRetry?: () => void
  title?: string
}

/** Error state for a list, widget or form (alert-error = error bg + error-content). */
export default function ErrorAlert({ error, onRetry, title }: ErrorAlertProps) {
  return (
    <div role="alert" className="alert alert-error">
      <AlertIcon />
      <div className="min-w-0">
        {title && <p className="font-semibold">{title}</p>}
        <p className="break-words">{errorMessage(error)}</p>
      </div>
      {onRetry && (
        <button type="button" className="btn btn-sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}
