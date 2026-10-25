// frontend/src/pages/inventory/__tests__/Inventory.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, within, waitFor } from '@testing-library/react'

const { search, getKardex, createAdjustment, getBranches, telefono } = vi.hoisted(() => ({
  search: vi.fn(), getKardex: vi.fn(), createAdjustment: vi.fn(), getBranches: vi.fn(), telefono: { valor: false },
}))
vi.mock('../../../hooks/useIsMobile', () => ({ useEsTelefono: () => telefono.valor }))
vi.mock('../../../api/products', () => ({ productsApi: { search } }))
vi.mock('../../../api/inventory', () => ({ inventoryApi: { getKardex, createAdjustment } }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches } }))

import { Inventory } from '../Inventory'
import { useAuthStore } from '../../../store/authStore'

const PRODUCTOS = [
  { id: 'p1', name: 'Blusa', sku: 'BLU', price: 100, cost: 40, stock_total: 3, is_active: true,
    variants: [{ id: 'v1', product_id: 'p1', sku: 'BLU', price: 100, cost: 40, stock_total: 3, variant_name: 'Estándar' }] },
  { id: 'p2', name: 'Falda', sku: 'FAL', price: 200, cost: 0, stock_total: 2, is_active: true,
    variants: [{ id: 'v2', product_id: 'p2', sku: 'FAL', price: 200, cost: 0, stock_total: 2, variant_name: 'Estándar' }] },
]
const MOVIMIENTO = { id: 1, movement_type: 'ADJUSTMENT_IN', qty_change: 2, qty_after: 3, reference: 'AJ-1', created_at: '2026-10-20T15:00:00Z', user_name: 'Mirna' }
const usuario = (role: string) => useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: 1, platform_role: 'NONE' } } as never)
const pintar = (ruta = '/inventory') => render(<MemoryRouter initialEntries={[ruta]}><Inventory /></MemoryRouter>)
const buscar = () => fireEvent.change(screen.getByPlaceholderText(/Buscar producto/), { target: { value: 'a' } })
const cabeceras = () => screen.getAllByRole('columnheader').map((th) => th.textContent)

beforeEach(() => {
  telefono.valor = false
  usuario('ADMINISTRADOR')
  search.mockReset().mockResolvedValue({ items: PRODUCTOS, total: 2, page: 0, pages: 1 })
  getKardex.mockReset().mockResolvedValue([])
  getBranches.mockReset().mockResolvedValue([{ id: 1, name: 'Roma', branch_type: 'STORE', is_active: true }])
})
afterEach(cleanup)

describe('Inventario (/inventory, fusión de Existencias)', () => {
  it('la administradora ve costo, importe a venta y a costo, y los totales de lo listado', async () => {
    pintar(); buscar()
    await screen.findByText('Blusa')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Inventario')
    expect(cabeceras()).toEqual(['SKU', 'Producto', 'Precio', 'Costo', 'Stock', 'Importe venta', 'Importe costo', ''])
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

  it('el gerente no ve costos ni la casilla "Solo sin costo", pero sí kardex y ajuste', async () => {
    usuario('GERENTE')
    pintar(); buscar()
    await screen.findByText('Blusa')
    expect(cabeceras()).toEqual(['SKU', 'Producto', 'Precio', 'Stock', 'Importe venta', ''])
    expect(screen.queryByLabelText('Solo sin costo')).toBeNull()
    fireEvent.click(screen.getAllByText('Kardex')[0])
    expect(await screen.findByText('Ajustar')).toBeTruthy()
  })

  it('la cajera tampoco ve costos (misma regla que la valuación)', async () => {
    usuario('CAJERO')
    pintar(); buscar()
    await screen.findByText('Blusa')
    expect(cabeceras()).toEqual(['SKU', 'Producto', 'Precio', 'Stock', 'Importe venta', ''])
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

  it('?q=&variant= siembra la búsqueda y abre el kardex de esa talla, con la columna "Por"', async () => {
    getKardex.mockResolvedValue([MOVIMIENTO])
    pintar('/inventory?q=BLU&variant=v1')
    await waitFor(() => expect(search).toHaveBeenCalledWith('BLU', 0, 30))
    await waitFor(() => expect(getKardex).toHaveBeenCalledWith('v1'))
    expect(await screen.findByText('Mirna')).toBeTruthy()
    expect(screen.getByText('Ajuste (+)')).toBeTruthy()
  })

  it('una respuesta vieja no pisa a la nueva: si la primera búsqueda llega tarde, manda la última', async () => {
    let resolverPrimera!: (v: unknown) => void
    search.mockReset()
      .mockImplementationOnce(() => new Promise((r) => { resolverPrimera = r }))
      .mockResolvedValue({ items: [PRODUCTOS[1]], total: 1, page: 0, pages: 1 })
    pintar()
    const caja = screen.getByPlaceholderText(/Buscar producto/)
    fireEvent.change(caja, { target: { value: 'b' } })
    fireEvent.change(caja, { target: { value: 'fa' } })
    await screen.findByText('Falda')
    resolverPrimera({ items: [PRODUCTOS[0]], total: 1, page: 0, pages: 1 })
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.getByText('Falda')).toBeTruthy()
    expect(screen.queryByText('Blusa')).toBeNull()
  })

  it('borrar la búsqueda descarta una respuesta que venía en camino', async () => {
    let resolverPrimera!: (v: unknown) => void
    search.mockReset().mockImplementationOnce(() => new Promise((r) => { resolverPrimera = r }))
    pintar()
    const caja = screen.getByPlaceholderText(/Buscar producto/)
    fireEvent.change(caja, { target: { value: 'b' } })
    fireEvent.change(caja, { target: { value: '' } })
    resolverPrimera({ items: [PRODUCTOS[0]], total: 1, page: 0, pages: 1 })
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByText('Blusa')).toBeNull()
    expect(screen.getByText('Busca un producto para ver su kardex')).toBeTruthy()
  })

  it.each([['escritorio', false], ['teléfono', true]])('si falla la búsqueda (%s) muestra el error con Reintentar, no «Sin resultados»', async (_n, tel) => {
    telefono.valor = tel
    search.mockReset()
      .mockRejectedValueOnce({ response: { data: { detail: 'Sin conexión con el servidor' } } })
      .mockResolvedValue({ items: PRODUCTOS, total: 2, page: 0, pages: 1 })
    pintar(); buscar()
    const alerta = await screen.findByRole('alert')
    expect(alerta.textContent).toContain('Sin conexión con el servidor')
    expect(alerta.querySelector('.text-dax-danger')).toBeTruthy()
    expect(screen.queryByText(/Sin resultados/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Reintentar/ }))
    await screen.findByText('Blusa')
    expect(search).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('en teléfono la vista de tarjetas también respeta costo por rol', async () => {
    telefono.valor = true
    usuario('GERENTE')
    pintar(); buscar()
    await screen.findByText('Blusa')
    expect(screen.queryByText('Costo')).toBeNull()
    expect(screen.queryByText('A costo')).toBeNull()
  })
})
