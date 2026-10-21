// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

// El formulario único se sustituye por un doble: aquí solo se prueba el envoltorio.
vi.mock('../../products/FormularioProducto', () => ({
  FormularioProducto: (p: { mode: string; productId?: string; variantId?: string; presentacion: string; onDone: (x: unknown) => void; onCancel: () => void }) => (
    <div>
      <span>doble:{p.mode}:{p.productId}:{p.variantId ?? '-'}:{p.presentacion}</span>
      <button onClick={() => p.onDone({ id: p.productId, name: 'Blusa', sku: 'BLU', price: 1 })}>guardar-doble</button>
      <button onClick={p.onCancel}>cancelar-doble</button>
    </div>
  ),
}))

const { default: EditarProductoPos } = await import('../EditarProductoPos')
const { Modal } = await import('../../ui/Modal')
afterEach(cleanup)

describe('EditarProductoPos', () => {
  it('monta el formulario único en edición dentro del Modal del kit', () => {
    render(<EditarProductoPos productId="p1" variantId="v2" onClose={() => {}} onGuardado={() => {}} />)
    expect(screen.getByText('Editar producto')).toBeTruthy()
    expect(screen.getByText('doble:edit:p1:v2:modal')).toBeTruthy()
  })

  it('sin talla manda variantId vacío (undefined), no null', () => {
    render(<EditarProductoPos productId="p1" variantId={null} onClose={() => {}} onGuardado={() => {}} />)
    expect(screen.getByText('doble:edit:p1:-:modal')).toBeTruthy()
  })

  it('al guardar avisa con el producto; al cancelar cierra', () => {
    const onGuardado = vi.fn(); const onClose = vi.fn()
    render(<EditarProductoPos productId="p1" onClose={onClose} onGuardado={onGuardado} />)
    fireEvent.click(screen.getByText('guardar-doble'))
    expect(onGuardado).toHaveBeenCalledWith(expect.objectContaining({ id: 'p1', name: 'Blusa' }))
    fireEvent.click(screen.getByText('cancelar-doble'))
    expect(onClose).toHaveBeenCalled()
  })

  it('no se cierra con Escape ni con el fondo (formulario largo)', () => {
    const onClose = vi.fn()
    render(<EditarProductoPos productId="p1" onClose={onClose} onGuardado={() => {}} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByRole('dialog'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('apilado sobre la ficha (otro Modal del kit): Escape no cierra ninguno de los dos y el scroll queda bloqueado', () => {
    const cerrarFicha = vi.fn(); const cerrarEditor = vi.fn()
    document.body.style.overflow = ''
    const { unmount } = render(
      <Modal open onClose={cerrarFicha} title="Blusa" closeOnEscape={false}>
        <p>ficha</p>
        <EditarProductoPos productId="p1" onClose={cerrarEditor} onGuardado={() => {}} />
      </Modal>,
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(cerrarEditor).not.toHaveBeenCalled()
    expect(cerrarFicha).not.toHaveBeenCalled()
    expect(document.body.style.overflow).toBe('hidden')
    unmount()
    expect(document.body.style.overflow).toBe('')
  })
})
