/**
 * ConfirmDialog — diálogo de confirmación promise-based.
 *
 * API imperativa:
 *   const ok = await confirm({ title, message, variant: 'danger' })
 *
 * API declarativa (hook):
 *   const confirm = useConfirm()
 *   const ok = await confirm({ ... })
 *
 * Uso: montar `<ConfirmDialogProvider>` cerca de la raíz del árbol
 * (en `main.tsx`). Soporta múltiples llamadas concurrentes — se encolan
 * y se muestran una a la vez. ESC cancela, Enter confirma, focus trap.
 */

import { createPortal } from 'react-dom'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

export type ConfirmVariant = 'danger' | 'warning' | 'info'

export interface ConfirmOptions {
  title: string
  message?: ReactNode
  confirmText?: string
  cancelText?: string
  variant?: ConfirmVariant
}

interface QueueItem {
  id: number
  options: ConfirmOptions
  resolve: (v: boolean) => void
}

// Module-level bridge: la función registrada por el Provider abierto.
// Si no hay provider montado, `confirm()` resuelve a `false` y loguea aviso.
type OpenFn = (options: ConfirmOptions) => Promise<boolean>
let activeOpenFn: OpenFn | null = null

/** Invoca el diálogo y retorna una Promise<boolean>. */
export function confirm(options: ConfirmOptions): Promise<boolean> {
  if (!activeOpenFn) {
    // Fallback silencioso — en producción el Provider SIEMPRE debe estar montado.
    console.warn('[ConfirmDialog] confirm() called without <ConfirmDialogProvider> mounted.')
    return Promise.resolve(false)
  }
  return activeOpenFn(options)
}

/** Hook equivalente — retorna la misma función `confirm`. */
export function useConfirm(): OpenFn {
  return confirm
}

const VARIANT_STYLES: Record<ConfirmVariant, { icon: string; accent: string; btn: string }> = {
  danger: {
    icon: 'fa-circle-exclamation text-red-400',
    accent: 'border-red-500/30',
    btn: 'bg-red-600 hover:bg-red-700 text-white',
  },
  warning: {
    icon: 'fa-triangle-exclamation text-amber-400',
    accent: 'border-amber-500/30',
    btn: 'bg-amber-600 hover:bg-amber-700 text-white',
  },
  info: {
    icon: 'fa-circle-info text-blue-400',
    accent: 'border-blue-500/30',
    btn: 'bg-indigo-600 hover:bg-indigo-700 text-white',
  },
}

interface DialogViewProps {
  options: ConfirmOptions
  onConfirm: () => void
  onCancel: () => void
}

function DialogView({ options, onConfirm, onCancel }: DialogViewProps) {
  const variant: ConfirmVariant = options.variant ?? 'info'
  const styles = VARIANT_STYLES[variant]
  const confirmBtnRef = useRef<HTMLButtonElement | null>(null)
  const cancelBtnRef = useRef<HTMLButtonElement | null>(null)

  // Focus inicial. Para danger, el botón cancelar (evita confirmar por accidente).
  useLayoutEffect(() => {
    const target = variant === 'danger' ? cancelBtnRef.current : confirmBtnRef.current
    target?.focus()
  }, [variant])

  // Focus trap + teclado. `data-modal-kit` en la raíz lo mete a la pila de
  // ui/Modal: con una confirmación encima, el Modal de abajo no atiende Escape.
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        onCancel()
      } else if (e.key === 'Enter') {
        const tag = (document.activeElement?.tagName ?? '').toLowerCase()
        if (tag !== 'button' || document.activeElement === confirmBtnRef.current) {
          e.preventDefault()
          onConfirm()
        }
      } else if (e.key === 'Tab') {
        const focusables = [cancelBtnRef.current, confirmBtnRef.current].filter(Boolean) as HTMLElement[]
        if (focusables.length === 0) return
        const currentIdx = focusables.indexOf(document.activeElement as HTMLElement)
        if (currentIdx === -1) {
          e.preventDefault()
          focusables[0].focus()
        } else {
          const nextIdx = e.shiftKey
            ? (currentIdx - 1 + focusables.length) % focusables.length
            : (currentIdx + 1) % focusables.length
          e.preventDefault()
          focusables[nextIdx].focus()
        }
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onCancel, onConfirm])

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center p-4 backdrop-blur-sm transition-opacity"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title"
      data-modal-kit=""
      onClick={(e) => { if (e.target === e.currentTarget) onCancel() }}
    >
      {/* `.dax-modal`: tope de alto y hoja inferior bajo `sm` (index.css §2). Colores del tema, no fijos. */}
      <div className={`dax-card dax-modal w-full max-w-md p-5 border ${styles.accent} shadow-2xl`} style={{ background: 'var(--dax-card-solid)' }}>
        <div className="flex items-start gap-3 mb-3">
          <i className={`fa-solid ${styles.icon} text-xl mt-0.5`} aria-hidden="true" />
          <h2 id="confirm-dialog-title" className="font-bold text-base leading-snug" style={{ color: 'var(--dax-text)' }}>
            {options.title}
          </h2>
        </div>
        {options.message && (
          <div className="text-sm leading-relaxed mb-5 ml-8" style={{ color: 'var(--dax-text-muted)' }}>{options.message}</div>
        )}
        <div className="dax-modal-footer -mx-5 px-5 flex items-center justify-end gap-2">
          <button ref={cancelBtnRef} type="button" onClick={onCancel} className="dax-btn-secondary text-sm">
            {options.cancelText ?? 'Cancelar'}
          </button>
          <button ref={confirmBtnRef} type="button" onClick={onConfirm}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${styles.btn}`}>
            {options.confirmText ?? 'Confirmar'}
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Provider que habilita `confirm()` imperativo en toda la app.
 * Montar una sola vez cerca de la raíz.
 */
export function ConfirmDialogProvider({ children }: { children: ReactNode }) {
  const [queue, setQueue] = useState<QueueItem[]>([])
  const nextIdRef = useRef(0)

  useEffect(() => {
    activeOpenFn = (options) =>
      new Promise<boolean>((resolve) => {
        const id = ++nextIdRef.current
        setQueue((q) => [...q, { id, options, resolve }])
      })
    return () => {
      activeOpenFn = null
    }
  }, [])

  const current = queue[0]

  const handleConfirm = () => {
    if (!current) return
    current.resolve(true)
    setQueue((q) => q.slice(1))
  }
  const handleCancel = () => {
    if (!current) return
    current.resolve(false)
    setQueue((q) => q.slice(1))
  }

  return (
    <>
      {children}
      {current && typeof document !== 'undefined'
        ? createPortal(
            <DialogView options={current.options} onConfirm={handleConfirm} onCancel={handleCancel} />,
            document.body,
          )
        : null}
    </>
  )
}

export default ConfirmDialogProvider
