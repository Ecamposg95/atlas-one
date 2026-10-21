// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, act, fireEvent } from '@testing-library/react'
import { useEffect } from 'react'
import { Modal } from '../Modal'

afterEach(cleanup)

// matchMedia falso que permite disparar `change` a mano (simula girar el
// teléfono / cruzar el corte `sm`).
type Oyente = (e: { matches: boolean; media: string }) => void
let oyentes: Oyente[] = []
let coincide = false
beforeEach(() => {
  oyentes = []
  coincide = false
  window.matchMedia = ((media: string) => ({
    get matches() { return coincide },
    media,
    onchange: null,
    addEventListener: (_: string, fn: Oyente) => { oyentes.push(fn) },
    removeEventListener: (_: string, fn: Oyente) => { oyentes = oyentes.filter(o => o !== fn) },
    addListener: (fn: Oyente) => { oyentes.push(fn) },
    removeListener: (fn: Oyente) => { oyentes = oyentes.filter(o => o !== fn) },
    dispatchEvent: () => true,
  })) as unknown as typeof window.matchMedia
})

let montajes = 0
function Contenido() {
  useEffect(() => { montajes++ }, [])
  return <div data-testid="contenido">cuerpo</div>
}

describe('Modal', () => {
  it('el panel lleva dax-modal y el pie dax-modal-footer', () => {
    render(
      <Modal open onClose={() => {}} title="Nuevo gasto" footer={<button>Guardar</button>}>
        <Contenido />
      </Modal>,
    )
    const panel = screen.getByRole('dialog').firstElementChild as HTMLElement
    expect(panel.classList.contains('dax-modal')).toBe(true)
    // el tope de alto ahora lo da .dax-modal (90dvh), no la utilidad
    expect(panel.classList.contains('max-h-[90vh]')).toBe(false)
    const pie = screen.getByRole('button', { name: 'Guardar' }).parentElement as HTMLElement
    expect(pie.classList.contains('dax-modal-footer')).toBe(true)
  })
  it('sin footer no pinta el pie', () => {
    render(<Modal open onClose={() => {}} title="t"><Contenido /></Modal>)
    expect(document.querySelector('.dax-modal-footer')).toBeNull()
  })
  it('la hoja inferior es CSS: cruzar el corte no remonta el contenido', () => {
    montajes = 0
    render(<Modal open onClose={() => {}} title="t" footer={<button>Ok</button>}><Contenido /></Modal>)
    const antes = screen.getByTestId('contenido')
    expect(montajes).toBe(1)
    act(() => {
      coincide = true
      oyentes.forEach(fn => fn({ matches: true, media: '(max-width: 639px)' }))
      window.dispatchEvent(new Event('resize'))
    })
    expect(montajes).toBe(1)
    expect(screen.getByTestId('contenido')).toBe(antes)
  })

  it('Escape cierra por defecto y no cierra con closeOnEscape={false}', () => {
    const cierres: string[] = []
    const { rerender } = render(<Modal open onClose={() => cierres.push('x')} title="T"><p>c</p></Modal>)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(cierres).toHaveLength(1)
    rerender(<Modal open onClose={() => cierres.push('x')} title="T" closeOnEscape={false}><p>c</p></Modal>)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(cierres).toHaveLength(1)
  })

  it('el botón de cierre usa dax-btn-icon (44 px en teléfono)', () => {
    render(<Modal open onClose={() => {}} title="T"><p>c</p></Modal>)
    expect(screen.getByLabelText('Cerrar').classList.contains('dax-btn-icon')).toBe(true)
  })
})

// Dos modales apilados (la ficha del POS con el editor encima): solo el de
// arriba atiende Escape, y el scroll del body se libera cuando cierra el último.
function Apilados({ onCerrarAbajo, onCerrarArriba, arriba }: { onCerrarAbajo: () => void; onCerrarArriba: () => void; arriba: boolean }) {
  return (
    <Modal open onClose={onCerrarAbajo} title="Abajo">
      <p>contenido de abajo</p>
      {arriba && (
        <Modal open onClose={onCerrarArriba} title="Arriba" closeOnEscape={false}>
          <p>contenido de arriba</p>
        </Modal>
      )}
    </Modal>
  )
}

describe('modales apilados', () => {
  it('Escape solo lo atiende el de arriba: con closeOnEscape={false} arriba, no cierra ninguno', () => {
    let abajo = 0, arriba = 0
    render(<Apilados onCerrarAbajo={() => abajo++} onCerrarArriba={() => arriba++} arriba />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(abajo).toBe(0)
    expect(arriba).toBe(0)
  })

  it('cerrado el de arriba, Escape vuelve a cerrar el de abajo', () => {
    let abajo = 0
    const { rerender } = render(<Apilados onCerrarAbajo={() => abajo++} onCerrarArriba={() => {}} arriba />)
    rerender(<Apilados onCerrarAbajo={() => abajo++} onCerrarArriba={() => {}} arriba={false} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(abajo).toBe(1)
  })

  it('el scroll del body se bloquea con el primero y se libera con el último, también al desmontarse juntos', () => {
    document.body.style.overflow = ''
    const { rerender, unmount } = render(<Apilados onCerrarAbajo={() => {}} onCerrarArriba={() => {}} arriba />)
    expect(document.body.style.overflow).toBe('hidden')
    rerender(<Apilados onCerrarAbajo={() => {}} onCerrarArriba={() => {}} arriba={false} />)
    expect(document.body.style.overflow).toBe('hidden')   // el de abajo sigue abierto
    unmount()
    expect(document.body.style.overflow).toBe('')
    const r2 = render(<Apilados onCerrarAbajo={() => {}} onCerrarArriba={() => {}} arriba />)
    r2.unmount()                                            // padre e hijo a la vez (el caso del bug)
    expect(document.body.style.overflow).toBe('')
  })
})
