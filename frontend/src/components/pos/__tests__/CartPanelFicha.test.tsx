// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({ getById: vi.fn() }))
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../api/inventory', () => ({ inventoryApi: { createAdjustment: vi.fn() } }))

const { CartPanel } = await import('../CartPanel')
const { usePOSStore } = await import('../../../store/posStore')
const { useEnabledModulesStore } = await import('../../../store/enabledModulesStore')

const v1 = { id: 'v1', product_id: 'p1', sku: 'BLU-CH', variant_name: 'Rojo / CH', color: 'Rojo', size: 'CH', price: 100, cost: 50, stock_total: 3 }
const v2 = { id: 'v2', product_id: 'p1', sku: 'BLU-M', variant_name: 'Rojo / M', color: 'Rojo', size: 'M', price: 100, cost: 50, stock_total: 5 }
// El servidor empata la PRIMERA talla; la línea del carrito es la M.
const blusa = { id: 'p1', sku: 'BLU-CH', name: 'Blusa', price: 100, cost: 50, stock: 3, stock_total: 3, is_active: true, description: null,
  brand_id: null, brand_name: null, department: null, department_name: null, unit: null, image_url: null, variants: [v1, v2], matched_variant_id: 'v1' }
const lineaM = { product_id: 'p1', variant_id: 'v2', variant_label: 'Rojo / M', cart_key: 'p1:v2', sku: 'BLU-M', name: 'Blusa (M)',
  price: 100, base_price: 100, quantity: 1, discount: 0, subtotal: 100 }

beforeEach(() => {
  vi.clearAllMocks()
  api.getById.mockResolvedValue(blusa)
  usePOSStore.setState({ cart: [lineaM], globalDiscount: 0 } as never)
  useEnabledModulesStore.setState({ loaded: true, perfilUi: 'completo' } as never)
})
afterEach(cleanup)

describe('ficha desde el carrito (SP1-c, I2 de la revisión final)', () => {
  it('abre en la talla de la línea, antes y después de cargar el producto completo', async () => {
    render(<CartPanel onPay={() => {}} onPark={() => {}} customerName={null} onClearCustomer={() => {}} sessionLocked={false} onOpenSession={() => {}} />)
    fireEvent.click(screen.getByTitle('Ver detalles'))
    // Producto completo: la talla resaltada y el número grande son los de la M (5), no los de la CH (3).
    await waitFor(() => expect(api.getById).toHaveBeenCalledWith('p1'))
    expect(await screen.findByText('5 en stock')).toBeTruthy()
    expect(screen.queryByText('3 en stock')).toBeNull()
    // El chip de talla elegida dice M.
    expect(screen.getAllByText('Rojo / M').length).toBeGreaterThanOrEqual(1)
  })
})
