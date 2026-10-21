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
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'

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
  /** Cerrar con la tecla Escape (default true). Apagar en formularios largos: Esc soltó lo capturado. */
  closeOnEscape?: boolean
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Modales apilados (p. ej. la ficha del POS con el editor encima): solo el de
// arriba atiende Escape y Tab, y el scroll del body se libera cuando cierra el
// ÚLTIMO. Antes cada modal restauraba "el overflow previo": al desmontarse
// padre e hijo juntos, el hijo devolvía `hidden` y la página quedaba sin scroll.
let candadosScroll = 0
let overflowPrevio = ''
// Un modal con otro modal del kit abierto DENTRO (en su árbol de React) no es el
// de arriba; entre los que no tienen hijos, el de arriba es el último en el DOM
// (los portales se añaden al body en el orden en que se abren).
const ContextoModal = createContext<(() => () => void) | null>(null)
// Raíz de cada modal abierto → cuántos modales del kit tiene abiertos dentro.
const hijosDe = new WeakMap<Element, () => number>()
function esElDeArriba(raiz: HTMLElement | null): boolean {
  if (!raiz) return false
  const libres = Array.from(document.querySelectorAll('[data-modal-kit]')).filter(r => (hijosDe.get(r)?.() ?? 0) === 0)
  return libres[libres.length - 1] === raiz
}

export function Modal({ open, onClose, title, children, footer, size = 'md', closeOnBackdrop = true, closeOnEscape = true }: ModalProps) {
  const panelRef = useRef<HTMLDivElement | null>(null)
  const restoreFocusRef = useRef<HTMLElement | null>(null)
  const raizRef = useRef<HTMLDivElement | null>(null)
  const hijosAbiertos = useRef(0)
  const registrarEnPadre = useContext(ContextoModal)

  // Un modal anidado se registra en el que lo contiene mientras esté abierto.
  useLayoutEffect(() => {
    if (!open || !registrarEnPadre) return
    return registrarEnPadre()
  }, [open, registrarEnPadre])
  const registrarHijo = useCallback(() => {
    hijosAbiertos.current++
    return () => { hijosAbiertos.current-- }
  }, [])
  // Se publica cuando la raíz ya existe (efecto pasivo: los refs ya están puestos).
  useEffect(() => {
    if (!open) return
    const raiz = raizRef.current
    if (!raiz) return
    hijosDe.set(raiz, () => hijosAbiertos.current)
    return () => { hijosDe.delete(raiz) }
  }, [open])

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
      if (!esElDeArriba(raizRef.current)) return
      if (e.key === 'Escape') {
        if (!closeOnEscape) return
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
  }, [open, onClose, closeOnEscape])

  // Scroll-lock del body mientras haya algún modal abierto (contador).
  useEffect(() => {
    if (!open) return
    if (candadosScroll === 0) {
      overflowPrevio = document.body.style.overflow
      document.body.style.overflow = 'hidden'
    }
    candadosScroll++
    return () => {
      candadosScroll--
      if (candadosScroll === 0) document.body.style.overflow = overflowPrevio
    }
  }, [open])

  if (!open || typeof document === 'undefined') return null

  return createPortal(
    <ContextoModal.Provider value={registrarHijo}>
    <div
      ref={raizRef}
      data-modal-kit=""
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
            className="dax-btn-icon w-8 h-8 grid place-items-center rounded-lg transition-colors hover:bg-black/5 dark:hover:bg-white/10"
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
    </div>
    </ContextoModal.Provider>,
    document.body,
  )
}

export default Modal
