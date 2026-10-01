// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, act } from '@testing-library/react'
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
})
