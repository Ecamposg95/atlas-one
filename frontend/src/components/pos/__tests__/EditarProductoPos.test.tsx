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
})
