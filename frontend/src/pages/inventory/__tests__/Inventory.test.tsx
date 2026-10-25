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
import { useToastStore } from '../../../store/toastStore'

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
const esperarDebounce = () => new Promise((r) => setTimeout(r, 350))
const cabeceras = () => screen.getAllByRole('columnheader').map((th) => th.textContent)

beforeEach(() => {
  telefono.valor = false
  usuario('ADMINISTRADOR')
  search.mockReset().mockResolvedValue({ items: PRODUCTOS, total: 2, page: 0, pages: 1 })
  getKardex.mockReset().mockResolvedValue([])
  createAdjustment.mockReset().mockResolvedValue(MOVIMIENTO)
  getBranches.mockReset().mockResolvedValue([
    { id: 1, name: 'Roma', branch_type: 'STORE', is_active: true },
    { id: 2, name: 'Bodega', branch_type: 'WAREHOUSE', is_active: true },
  ])
  useAuthStore.setState({ branch: null } as never)
  useToastStore.setState({ toasts: [] })
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
    await waitFor(() => expect(getKardex).toHaveBeenCalledWith('v1', 1))
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
    await esperarDebounce()          // la primera sale (queda pendiente)
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
    await esperarDebounce()
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

  it('el buscador espera 300 ms: teclear de corrido hace una sola petición, con el último texto', async () => {
    pintar()
    const caja = screen.getByPlaceholderText(/Buscar producto/)
    fireEvent.change(caja, { target: { value: 'b' } })
    fireEvent.change(caja, { target: { value: 'bl' } })
    fireEvent.change(caja, { target: { value: 'blu' } })
    expect(search).not.toHaveBeenCalled()
    await esperarDebounce()
    await screen.findByText('Blusa')
    expect(search).toHaveBeenCalledTimes(1)
    expect(search).toHaveBeenCalledWith('blu', 0, 30)
    expect(screen.getByLabelText('Buscar producto por nombre o SKU')).toBe(caja)
  })

  it('un kardex que llega tarde de otra talla no pisa al de la talla abierta después', async () => {
    let resolverV1!: (v: unknown) => void
    getKardex.mockReset()
      .mockImplementationOnce(() => new Promise((r) => { resolverV1 = r }))
      .mockResolvedValue([{ ...MOVIMIENTO, id: 2, user_name: 'Jose' }])
    pintar(); buscar()
    await screen.findByText('Blusa')
    fireEvent.click(screen.getAllByText('Kardex')[0])
    fireEvent.click(screen.getByText('Cerrar'))
    fireEvent.click(screen.getAllByText('Kardex')[1])
    await screen.findByText('Jose')
    resolverV1([{ ...MOVIMIENTO, id: 1, user_name: 'Mirna' }])
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.getByText('Jose')).toBeTruthy()
    expect(screen.queryByText('Mirna')).toBeNull()
  })

  it('la cajera que entra por ?q=&variant= ve el kardex de su sucursal, sin casilla ni costos', async () => {
    usuario('CAJERO')
    getKardex.mockResolvedValue([MOVIMIENTO])
    pintar('/inventory?q=BLU&variant=v1')
    await waitFor(() => expect(getKardex).toHaveBeenCalledWith('v1', 1))
    expect(await screen.findByText('Mirna')).toBeTruthy()
    expect(screen.queryByLabelText('Solo sin costo')).toBeNull()
    expect(screen.queryByText('Costo')).toBeNull()
    expect(screen.queryByText('$40.00')).toBeNull()
  })

  it('en teléfono hay una tarjeta resumen con los totales (a costo solo para oficina)', async () => {
    telefono.valor = true
    pintar(); buscar()
    await screen.findByText('Blusa')
    const t = await screen.findByTestId('totales-telefono')
    expect(t.textContent).toContain('5 pzas')
    expect(t.textContent).toContain('$700.00 a venta')
    expect(t.textContent).toContain('$120.00 a costo')
    cleanup()
    usuario('GERENTE')
    pintar(); buscar()
    await screen.findByText('Blusa')
    expect((await screen.findByTestId('totales-telefono')).textContent).not.toContain('a costo')
  })

  // A5: el kardex inicial pide una sucursal; un admin sin sucursal propia usa la activa.
  it('?variant= de un admin sin sucursal propia pide el kardex de la sucursal activa', async () => {
    useAuthStore.setState({
      user: { id: 1, username: 'u', role: 'ADMINISTRADOR', branch_id: null, platform_role: 'NONE' },
      branch: { id: 5, name: 'Centro', branch_type: 'STORE', is_headquarters: false },
    } as never)
    pintar('/inventory?q=BLU&variant=v1')
    await waitFor(() => expect(getKardex).toHaveBeenCalledWith('v1', 5))
  })
})

describe('Ajuste de existencia (B1)', () => {
  const abrirAjuste = async () => {
    pintar(); buscar()
    await screen.findByText('Blusa')
    fireEvent.click(screen.getAllByText('Kardex')[0])
    fireEvent.click(await screen.findByText('Ajustar'))
    return await screen.findByRole('dialog')
  }
  const llenar = (dialogo: HTMLElement) => {
    fireEvent.change(within(dialogo).getByLabelText(/Cantidad/), { target: { value: '5' } })
    fireEvent.change(within(dialogo).getByLabelText('Motivo'), { target: { value: 'Conteo' } })
  }
  const textos = (tipo: string) => useToastStore.getState().toasts.filter((t) => t.type === tipo).map((t) => t.message)

  it('el administrador elige la sucursal, se guarda y el kardex se refresca con ESA sucursal', async () => {
    const dialogo = await abrirAjuste()
    fireEvent.change(within(dialogo).getByLabelText('Sucursal'), { target: { value: '2' } })
    llenar(dialogo)
    fireEvent.click(within(dialogo).getByRole('button', { name: /Ajustar/ }))
    await waitFor(() => expect(createAdjustment).toHaveBeenCalledWith(
      expect.objectContaining({ variant_id: 'v1', quantity: 5, branch_id: 2, reason: 'Conteo' })))
    await waitFor(() => expect(getKardex).toHaveBeenLastCalledWith('v1', 2))
    expect(textos('success')).toContain('Ajuste guardado')
    expect(textos('error')).toEqual([])
  })

  it('si el ajuste se guardó y falla el refresco del kardex, avisa que SÍ se guardó (no "No se guardó nada")', async () => {
    getKardex.mockReset().mockResolvedValueOnce([]).mockRejectedValue(new Error('red'))
    const dialogo = await abrirAjuste()
    fireEvent.change(within(dialogo).getByLabelText('Sucursal'), { target: { value: '1' } })
    llenar(dialogo)
    fireEvent.click(within(dialogo).getByRole('button', { name: /Ajustar/ }))
    await waitFor(() => expect(textos('warning')).toContain('Ajuste guardado; no se pudo refrescar el kardex'))
    expect(textos('success')).toContain('Ajuste guardado')
    expect(textos('error')).toEqual([])
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('si el POST falla sí dice que no se guardó nada y deja el modal abierto', async () => {
    createAdjustment.mockReset().mockRejectedValue({ response: { data: { detail: 'Stock insuficiente' } } })
    const dialogo = await abrirAjuste()
    fireEvent.change(within(dialogo).getByLabelText('Sucursal'), { target: { value: '1' } })
    llenar(dialogo)
    fireEvent.click(within(dialogo).getByRole('button', { name: /Ajustar/ }))
    await waitFor(() => expect(textos('error').length).toBe(1))
    expect(textos('success')).toEqual([])
    expect(screen.getByRole('dialog')).toBeTruthy()
  })

  it.each([['CAJERO'], ['GERENTE']])('%s no puede elegir otra sucursal: el select queda fijo en la suya y deshabilitado', async (rol) => {
    usuario(rol)
    const dialogo = await abrirAjuste()
    const sel = within(dialogo).getByLabelText('Sucursal') as HTMLSelectElement
    expect(sel.disabled).toBe(true)
    expect(sel.value).toBe('1')
    llenar(dialogo)
    fireEvent.click(within(dialogo).getByRole('button', { name: /Ajustar/ }))
    await waitFor(() => expect(createAdjustment).toHaveBeenCalledWith(expect.objectContaining({ branch_id: 1 })))
    await waitFor(() => expect(getKardex).toHaveBeenLastCalledWith('v1', 1))
  })
})
