// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react'

const api = vi.hoisted(() => ({
  getById: vi.fn(),
  createAdjustment: vi.fn(),
}))
vi.mock('../../../api/products', () => ({ productsApi: { getById: api.getById } }))
vi.mock('../../../api/inventory', () => ({ inventoryApi: { createAdjustment: api.createAdjustment } }))
vi.mock('../../../store/toastStore', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const v1 = { id: 'v1', product_id: 'p1', sku: 'BLU-CH', variant_name: 'Rojo / CH', color: 'Rojo', size: 'CH', price: 100, cost: 50, stock_total: 3 }
const v2 = { id: 'v2', product_id: 'p1', sku: 'BLU-M', variant_name: 'Rojo / M', color: 'Rojo', size: 'M', price: 100, cost: 50, stock_total: 0 }
const blusa = {
  id: 'p1', sku: 'BLU-CH', name: 'Blusa', price: 100, cost: 50, stock: 3, stock_total: 3, is_active: true,
  description: 'Lino', brand_id: 'b1', brand_name: 'Nike', department: null, department_name: 'Blusas', unit: null, image_url: null,
  barcode: '750', has_iva: true, tax_rate: 16, variants: [v1, v2], matched_variant_id: 'v1',
  prices: [{ id: 't1', price_name: 'Mayoreo', min_quantity: 6, unit_price: 90 }],
} as never

// Editor doble: solo importa que se abra con el id y la talla, y que avise al guardar.
vi.mock('../EditarProductoPos', () => ({
  default: (p: { productId: string; variantId?: string | null; onGuardado: (x: unknown) => void; onClose: () => void }) => (
    <div>
      <span>editor:{p.productId}:{p.variantId ?? '-'}</span>
      <button onClick={() => p.onGuardado({ ...(blusa as object), name: 'Blusa nueva', price: 150 })}>guardar-editor</button>
      <button onClick={p.onClose}>cerrar-editor</button>
    </div>
  ),
}))

const { ProductDetailModal } = await import('../modals/ProductDetailModal')
const { useAuthStore } = await import('../../../store/authStore')

const cajera = { id: 2, username: 'caja', role: 'CAJERO', branch_id: 20 }

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: cajera } as never)
})
afterEach(cleanup)

describe('ficha de consulta del POS (SP1-c)', () => {
  it('sin producto no pinta nada', () => {
    const { container } = render(<ProductDetailModal product={null} onClose={() => {}} />)
    expect(container.innerHTML).toBe('')
    expect(document.querySelector('[role=dialog]')).toBeNull()
  })

  it('pinta existencia y precio por talla, los escalones y la meta', () => {
    render(<ProductDetailModal product={blusa} onClose={() => {}} onAddToCart={() => {}} canEdit />)
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Blusa')).toBeTruthy()
    expect(within(dialog).getByText('BLU-CH')).toBeTruthy()
    expect(within(dialog).getByText('3 en stock')).toBeTruthy()
    expect(within(dialog).getByText('Rojo / M')).toBeTruthy()
    expect(within(dialog).getByText('sin existencia')).toBeTruthy()
    expect(within(dialog).getByText('Mayoreo')).toBeTruthy()
    expect(within(dialog).getByText('mín. 6u')).toBeTruthy()
    expect(within(dialog).getByText('Nike')).toBeTruthy()
    expect(within(dialog).getByText('Con IVA 16%')).toBeTruthy()
    expect(within(dialog).getByText('Lino')).toBeTruthy()
    expect(within(dialog).getByRole('button', { name: 'Agregar al carrito' })).toBeTruthy()
  })

  it('sin permiso de edición: ni Editar ni Agregar existencia, pero sí al carrito', () => {
    render(<ProductDetailModal product={blusa} onClose={() => {}} onAddToCart={() => {}} canEdit={false} />)
    expect(screen.queryByText('Editar')).toBeNull()
    expect(screen.queryByText('Agregar existencia')).toBeNull()
    expect(screen.getByRole('button', { name: 'Agregar al carrito' })).toBeTruthy()
  })

  it('Editar abre el formulario único con el producto y la talla; guardar refresca la ficha y avisa', async () => {
    const onSaved = vi.fn()
    render(<ProductDetailModal product={blusa} onClose={() => {}} canEdit onSaved={onSaved} />)
    fireEvent.click(screen.getByText('Editar'))
    expect(await screen.findByText('editor:p1:v1')).toBeTruthy()
    fireEvent.click(screen.getByText('guardar-editor'))
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ name: 'Blusa nueva' })))
    expect(screen.queryByText(/^editor:/)).toBeNull()
    expect(screen.getByText('Blusa nueva')).toBeTruthy()
  })

  it('cancelar el editor lo cierra sin avisar y la ficha sigue', async () => {
    const onSaved = vi.fn()
    render(<ProductDetailModal product={blusa} onClose={() => {}} canEdit onSaved={onSaved} />)
    fireEvent.click(screen.getByText('Editar'))
    fireEvent.click(await screen.findByText('cerrar-editor'))
    expect(screen.queryByText(/^editor:/)).toBeNull()
    expect(onSaved).not.toHaveBeenCalled()
    expect(screen.getByText('Blusa')).toBeTruthy()
  })

  it('Agregar existencia ajusta la talla elegida en la sucursal de la cajera y recarga', async () => {
    api.createAdjustment.mockResolvedValue({})
    api.getById.mockResolvedValue({ ...(blusa as object), stock_total: 8, variants: [{ ...v1, stock_total: 8 }, v2] })
    const onSaved = vi.fn()
    render(<ProductDetailModal product={blusa} onClose={() => {}} canEdit onSaved={onSaved} />)
    fireEvent.click(screen.getByText('Agregar existencia'))
    fireEvent.change(screen.getByLabelText('Cantidad'), { target: { value: '5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Registrar entrada' }))
    await waitFor(() => expect(api.createAdjustment).toHaveBeenCalledWith({ variant_id: 'v1', quantity: 5, branch_id: 20, reason: 'Reposición POS' }))
    await screen.findByText('+5 agregadas al stock')
    expect(onSaved).toHaveBeenCalled()
    expect(screen.getByText('8 en stock')).toBeTruthy()
  })

  it('la talla a ajustar sigue al selector', async () => {
    api.createAdjustment.mockResolvedValue({})
    api.getById.mockResolvedValue(blusa)
    render(<ProductDetailModal product={blusa} onClose={() => {}} canEdit />)
    fireEvent.click(screen.getByText('Agregar existencia'))
    fireEvent.change(screen.getByLabelText(/a ajustar$/), { target: { value: 'v2' } })
    fireEvent.change(screen.getByLabelText('Cantidad'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Registrar entrada' }))
    await waitFor(() => expect(api.createAdjustment).toHaveBeenCalledWith(expect.objectContaining({ variant_id: 'v2', quantity: 2 })))
  })

  it('cajera sin sucursal: aviso y ninguna llamada', async () => {
    useAuthStore.setState({ user: { ...cajera, branch_id: null } } as never)
    render(<ProductDetailModal product={blusa} onClose={() => {}} canEdit />)
    fireEvent.click(screen.getByText('Agregar existencia'))
    fireEvent.change(screen.getByLabelText('Cantidad'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Registrar entrada' }))
    expect(await screen.findByText('Tu usuario no tiene sucursal asignada')).toBeTruthy()
    expect(api.createAdjustment).not.toHaveBeenCalled()
  })

  it('Agregar al carrito manda el producto y cierra; sin existencia no hay botón', () => {
    const onAdd = vi.fn(); const onClose = vi.fn()
    render(<ProductDetailModal product={blusa} onClose={onClose} onAddToCart={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: 'Agregar al carrito' }))
    expect(onAdd).toHaveBeenCalledWith(blusa)
    expect(onClose).toHaveBeenCalled()
    cleanup()
    render(<ProductDetailModal product={{ ...(blusa as object), stock_total: 0, matched_variant_id: 'v2' } as never} onClose={() => {}} onAddToCart={onAdd} />)
    expect(screen.queryByRole('button', { name: 'Agregar al carrito' })).toBeNull()
    expect(screen.getByText('Sin stock')).toBeTruthy()
  })

  it('producto parcial del carrito (sin tallas): se pinta y Editar lleva su id', async () => {
    const parcial = { id: 'p9', sku: 'X', name: 'Cinturón', description: null, brand_id: null, brand_name: null, department: null,
      department_name: null, unit: null, cost: 0, price: 50, stock: 1, stock_total: 1, image_url: null, is_active: true } as never
    render(<ProductDetailModal product={parcial} onClose={() => {}} canEdit />)
    expect(screen.getByText('Cinturón')).toBeTruthy()
    expect(screen.getByText('1 en stock')).toBeTruthy()
    fireEvent.click(screen.getByText('Editar'))
    expect(await screen.findByText('editor:p9:-')).toBeTruthy()
  })
})
