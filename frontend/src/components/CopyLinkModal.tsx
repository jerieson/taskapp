import { useId, useRef, useState, type ReactNode } from 'react'

import { CheckCircleIcon, CopyIcon } from './icons'
import Modal from './Modal'
import { useToast } from './toast-context'

interface CopyLinkModalProps {
  /** The link to show; the modal is open while this is set. */
  url: string | null
  title: string
  children?: ReactNode
  onClose: () => void
}

/** Shows a one-time link (invite, password reset) with a copy button. */
export default function CopyLinkModal({ url, title, children, onClose }: CopyLinkModalProps) {
  const toast = useToast()
  const inputRef = useRef<HTMLInputElement>(null)
  const inputId = useId()
  const [copied, setCopied] = useState(false)

  async function copy() {
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      toast.success('Link copied')
    } catch {
      // Clipboard API unavailable (e.g. plain http on a non-localhost host).
      inputRef.current?.select()
      toast.info('Press Ctrl+C (or ⌘C) to copy the selected link')
    }
  }

  function close() {
    setCopied(false)
    onClose()
  }

  return (
    <Modal
      open={url !== null}
      title={title}
      onClose={close}
      actions={
        <button type="button" className="btn btn-primary" onClick={close}>
          Done
        </button>
      }
    >
      <div className="flex flex-col gap-3">
        {children && <div className="text-sm">{children}</div>}
        <label htmlFor={inputId} className="sr-only">
          Link
        </label>
        <div className="join w-full">
          <input
            ref={inputRef}
            id={inputId}
            className="input join-item w-full min-w-0 font-mono text-sm"
            value={url ?? ''}
            readOnly
            onFocus={(event) => event.currentTarget.select()}
          />
          <button type="button" className="btn btn-secondary join-item" onClick={() => void copy()}>
            {copied ? <CheckCircleIcon /> : <CopyIcon />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
        <p className="text-sm text-base-content/80">
          This link is shown only now. Send it to the person yourself; it works once.
        </p>
      </div>
    </Modal>
  )
}
