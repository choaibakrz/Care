/** One confirmation dialog for the whole panel. `askConfirm` resolves true or false. */
import { useEffect, useRef } from 'react'
import { AlertTriangle } from 'lucide-react'
import { create } from 'zustand'

interface ConfirmRequest {
  title: string
  body: string
  confirmLabel: string
  danger: boolean
  resolve: (answer: boolean) => void
}

const useConfirmStore = create<{ request: ConfirmRequest | null }>(() => ({ request: null }))

export function askConfirm(options: { title: string; body: string; confirmLabel: string; danger?: boolean }): Promise<boolean> {
  return new Promise((resolve) => {
    useConfirmStore.getState().request?.resolve(false)
    useConfirmStore.setState({ request: { ...options, danger: options.danger ?? false, resolve } })
  })
}

function answer(value: boolean): void {
  const { request } = useConfirmStore.getState()
  useConfirmStore.setState({ request: null })
  request?.resolve(value)
}

export function ConfirmHost() {
  const request = useConfirmStore((state) => state.request)
  const confirmButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!request) return undefined
    confirmButton.current?.focus()
    const onKey = (event: KeyboardEvent): void => { if (event.key === 'Escape') answer(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [request])

  if (!request) return null
  return (
    <div className="dialog-backdrop" onClick={() => answer(false)}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title" onClick={(event) => event.stopPropagation()}>
        <span className={`dialog-icon ${request.danger ? 'is-danger' : ''}`}><AlertTriangle size={20} /></span>
        <h2 id="dialog-title">{request.title}</h2>
        <p>{request.body}</p>
        <div className="dialog-actions">
          <button type="button" className="button is-ghost" onClick={() => answer(false)}>Keep going</button>
          <button ref={confirmButton} type="button" className={`button ${request.danger ? 'is-danger' : 'is-primary'}`} onClick={() => answer(true)}>{request.confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}
