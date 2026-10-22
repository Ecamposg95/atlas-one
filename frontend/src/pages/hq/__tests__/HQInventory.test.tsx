// frontend/src/pages/hq/__tests__/HQInventory.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react'

const { search, getKardex, createAdjustment, getBranches } = vi.hoisted(() => ({
  search: vi.fn(), getKardex: vi.fn(), createAdjustment: vi.fn(), getBranches: vi.fn(),
}))
vi.mock('../../../api/products', () => ({ productsApi: { search } }))
vi.mock('../../../api/inventory', () => ({ inventoryApi: { getKardex, createAdjustment } }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches } }))

import { HQInventory } from '../HQInventory'
import { useAuthStore } from '../../../store/authStore'

const PRODUCTOS = [
  { id: 'p1', name: 'Blusa', sku: 'BLU', price: 100, cost: 40, stock_total: 3, is_active: true,
    variants: [{ id: 'v1', product_id: 'p1', sku: 'BLU', price: 100, cost: 40, stock_total: 3, variant_name: 'Estándar' }] },
  { id: 'p2', name: 'Falda', sku: 'FAL', price: 200, cost: 0, stock_total: 2, is_active: true,
    variants: [{ id: 'v2', product_id: 'p2', sku: 'FAL', price: 200, cost: 0, stock_total: 2, variant_name: 'Estándar' }] },
]
const usuario = (role: string) => useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: 1 } } as never)
const pintar = () => render(<MemoryRouter><HQInventory /></MemoryRouter>)
const buscar = () => fireEvent.change(screen.getByPlaceholderText(/Buscar producto/), { target: { value: 'a' } })

beforeEach(() => {
  usuario('ADMINISTRADOR')
  search.mockReset().mockResolvedValue({ items: PRODUCTOS, total: 2, page: 0, pages: 1 })
  getKardex.mockReset().mockResolvedValue([])
  getBranches.mockReset().mockResolvedValue([{ id: 1, name: 'Roma', branch_type: 'STORE', is_active: true }])
})
afterEach(cleanup)

describe('HQInventory (SP6)', () => {
  it('la administradora ve costo, importe a venta y a costo, y los totales de lo listado', async () => {
    pintar(); buscar()
    await screen.findByText('Blusa')
    const cabeceras = screen.getAllByRole('columnheader').map((th) => th.textContent)
    expect(cabeceras).toEqual(['SKU', 'Producto', 'Precio', 'Costo', 'Stock', 'Importe venta', 'Importe costo', ''])
    const tot = screen.getByTestId('totales').textContent
    expect(tot).toContain('5')          // 3 + 2 piezas
    expect(tot).toContain('$700.00')    // 300 + 400 a venta
    expect(tot).toContain('$120.00')    // 120 + 0 a costo
    expect(screen.getByText('sin costo')).toBeTruthy()
  })

  it('"Solo sin costo" deja los renglones con costo nulo o cero', async () => {
    pintar(); buscar()
    await screen.findByText('Blusa')
    fireEvent.click(screen.getByLabelText('Solo sin costo'))
    expect(screen.queryByText('Blusa')).toBeNull()
    expect(screen.getByText('Falda')).toBeTruthy()
    expect(screen.getByTestId('totales').textContent).toContain('$400.00')
  })

  it('un rol que no ve costos no recibe las columnas de costo', async () => {
    usuario('GERENTE')
    pintar(); buscar()
    await screen.findByText('Blusa')
    const cabeceras = screen.getAllByRole('columnheader').map((th) => th.textContent)
    expect(cabeceras).toEqual(['SKU', 'Producto', 'Precio', 'Stock', 'Importe venta', ''])
  })

  it('el ajuste abre el Modal del kit (role dialog) desde el kardex', async () => {
    pintar(); buscar()
    await screen.findByText('Blusa')
    fireEvent.click(screen.getAllByText('Kardex')[0])
    fireEvent.click(await screen.findByText('Ajustar'))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('Ajuste de inventario')).toBeTruthy()
    expect(within(dialogo).getByLabelText('Cerrar')).toBeTruthy()
  })
})
