/**
 * Modal — diálogo compartido y accesible del kit Atlas One.
 *
 * Reemplaza los overlays ad-hoc (`fixed inset-0 ...`) repetidos por página.
 * Accesibilidad incluida: role="dialog", aria-modal, focus inicial y trap,
 * Escape para cerrar, scroll-lock del body y retorno del foco al disparador.
 *
 * Uso:
 *   <Modal open={open} onClose={() => setOpen(false)} title="Nuevo gasto" size="md"
 *          footer={<>
 *            <button className="dax-btn-secondary" onClick={close}>Cancelar</button>
 *            <button className="dax-btn-primary" onClick={save}>Guardar</button>
 *          </>}>
 *     ...campos...
 *   </Modal>
 */
import { createPortal } from 'react-dom'
import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'

const SIZES = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
} as const

export interface ModalProps {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
  footer?: ReactNode
  size?: keyof typeof SIZES
  /** Cerrar al hacer clic en el fondo (default true). Apagar en flujos que no deben perderse por un clic accidental. */
  closeOnBackdrop?: boolean
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Modal({ open, onClose, title, children, footer, size = 'md', closeOnBackdrop = true }: ModalProps) {
  const panelRef = useRef<HTMLDivElement | null>(null)
  const restoreFocusRef = useRef<HTMLElement | null>(null)

  // Foco inicial al abrir + retorno del foco al cerrar.
  useLayoutEffect(() => {
    if (!open) return
    restoreFocusRef.current = document.activeElement as HTMLElement | null
    const first = panelRef.current?.querySelector<HTMLElement>(FOCUSABLE)
    ;(first ?? panelRef.current)?.focus()
    return () => restoreFocusRef.current?.focus?.()
  }, [open])

  // Escape + focus trap.
  useEffect(() => {
    if (!open) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panelRef.current) return
      const focusables = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus()
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  // Scroll-lock del body mientras el modal está abierto.
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [open])

  if (!open || typeof document === 'undefined') return null

  return createPortal(
    <div
      className="fixed inset-0 z-[900] flex items-center justify-center p-4"
      style={{ background: 'var(--dax-modal-backdrop)', backdropFilter: 'blur(4px)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="atlas-modal-title"
      onClick={(e) => { if (closeOnBackdrop && e.target === e.currentTarget) onClose() }}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        // `.dax-modal` da el tope de alto (90dvh) y, bajo `sm`, la hoja
        // inferior a todo lo ancho (ver `index.css §2`). Es CSS puro: cruzar
        // el corte no remonta el contenido ni pierde lo capturado.
        className={`dax-modal w-full ${SIZES[size]} rounded-xl flex flex-col outline-none`}
        style={{
          background: 'var(--dax-card-solid)',
          border: '1px solid var(--dax-border)',
          boxShadow: 'var(--dax-shadow-lg)',
          color: 'var(--dax-text)',
        }}
      >
        <div className="flex items-center justify-between gap-4 px-5 pt-4 pb-3" style={{ borderBottom: '1px solid var(--dax-border-dim)' }}>
          <h2 id="atlas-modal-title" className="font-bold text-base leading-snug">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="w-8 h-8 grid place-items-center rounded-lg transition-colors hover:bg-black/5 dark:hover:bg-white/10"
            style={{ color: 'var(--dax-text-muted)' }}
          >
            <i className="fa-solid fa-xmark" />
          </button>
        </div>

        <div className="px-5 py-4 overflow-y-auto">{children}</div>

        {footer && (
          // `.dax-modal-footer`: pie pegado abajo, visible con el teclado
          // abierto. Su `padding-top` (0.75rem) vive fuera de @layer y le
          // ganaría a `py-4`; el inline lo devuelve a 1rem para que
          // escritorio quede igual que antes.
          <div
            className="dax-modal-footer flex items-center justify-end gap-2 px-5 py-4"
            style={{ borderTop: '1px solid var(--dax-border-dim)', paddingTop: '1rem' }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}

export default Modal
