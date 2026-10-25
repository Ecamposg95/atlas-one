// frontend/src/pages/sales/__tests__/SalesHistory.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react'

const { list, getStats, getBranches, telefono } = vi.hoisted(() => ({ list: vi.fn(), getStats: vi.fn(), getBranches: vi.fn(), telefono: { valor: false } }))
vi.mock('../../../hooks/useIsMobile', () => ({ useEsTelefono: () => telefono.valor }))
vi.mock('../../../api/sales', () => ({ salesApi: { list, getStats } }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches } }))
vi.mock('../../../api/printer', () => ({ printerApi: { getTicketBase64: vi.fn(), printViaAgent: vi.fn() } }))
vi.mock('../../../store/posStore', () => ({
  usePOSStore: (sel: (s: { printerName: string | null }) => unknown) => sel({ printerName: null }),
}))
vi.mock('../../../components/pos/modals/ReturnModal', () => ({ ReturnModal: () => <div data-testid="return-modal" /> }))
vi.mock('../../../components/pos/modals/ReprintPinModal', () => ({ ReprintPinModal: () => <div data-testid="pin-modal" /> }))

import { SalesHistory } from '../SalesHistory'
import { useAuthStore } from '../../../store/authStore'
import { rangoPreset } from '../../reports/presetsReportes'
import { useToastStore } from '../../../store/toastStore'

const hoy = rangoPreset('hoy')
const VENTA = {
  id: 'venta-1', series: 'A', folio: 41, status: 'PAID', total_amount: 250, subtotal: 250, tax_amount: 0,
  created_at: '2026-10-20T15:00:00Z', customer_name: null, branch_id: 1, branch_name: 'Roma',
  payments: [{ method: 'CASH', amount: 250 }],
  lines: [{ description: 'Blusa', sku: 'BLU', quantity: 1, unit_price: '250', total_line: '250' }],
}
const STATS = { total_sales: 250, total_transactions: 1, average_ticket: 250, payment_methods: { CASH: 250 }, refund_count: 0, refund_total: 0, peak_hour: '15:00' }
const SUC = (id: number, name: string, can_sell = true) =>
  ({ id, name, branch_type: 'STORE', address: null, phone: null, is_headquarters: false, is_active: true, can_sell })
const usuario = (role: string, branch_id: number | null = null) =>
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id, platform_role: 'NONE' } } as never)
const pintar = () => render(<MemoryRouter><SalesHistory /></MemoryRouter>)
const cabeceras = () => screen.getAllByRole('columnheader').map((th) => th.textContent)

beforeEach(() => {
  telefono.valor = false
  useToastStore.setState({ toasts: [] })
  list.mockReset().mockResolvedValue({ items: [VENTA], total: 1, page: 0, pages: 1 })
  getStats.mockReset().mockResolvedValue(STATS)
  getBranches.mockReset().mockResolvedValue([SUC(1, 'Roma'), SUC(2, 'Condesa')])
})
afterEach(cleanup)

describe('Ventas (/sales, fusión de HQSalesLog)', () => {
  it('la cajera arranca en Hoy, solo estados cerrados, sin pedir sucursales ni mandar branch_id; el título es Ventas', async () => {
    usuario('CAJERO', 1)
    pintar()
    await screen.findByText('A-0041')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Ventas')
    expect(screen.getByRole('button', { name: 'Hoy' }).getAttribute('aria-pressed')).toBe('true')
    expect(list).toHaveBeenCalledWith({
      start_date: hoy.inicio, end_date: hoy.fin, limit: 100, skip: 0, statuses: 'PAID,REFUNDED_PARTIAL,REFUNDED_TOTAL,CANCELLED',
    })
    expect(getStats).toHaveBeenCalledWith({ start_date: hoy.inicio, end_date: hoy.fin })
    expect((screen.getByLabelText('Incluir abiertas/borradores') as HTMLInputElement).checked).toBe(false)
    expect(getBranches).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(cabeceras()).not.toContain('Sucursal')
  })

  it('la cajera conserva Ver, Reimprimir y Devolver; el detalle abre el Modal del kit', async () => {
    usuario('CAJERO', 1)
    pintar()
    await screen.findByText('A-0041')
    expect(screen.getByRole('button', { name: /Reimprimir/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Devolver/ })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Ver' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('Blusa')).toBeTruthy()
    expect(within(dialogo).getByRole('button', { name: /Registrar devolución/ })).toBeTruthy()
  })

  it('la administradora con dos sucursales que venden ve el selector y la columna Sucursal; al elegir una manda branch_id', async () => {
    usuario('ADMINISTRADOR')
    pintar()
    await screen.findByText('A-0041')
    const selector = await screen.findByLabelText('Sucursal')
    expect(cabeceras()).toContain('Sucursal')
    expect(list.mock.calls[0][0]).not.toHaveProperty('branch_id')
    // HQ veía abiertas y borradores por defecto (HQSalesLog): la casilla arranca encendida y no viaja `statuses`.
    expect((screen.getByLabelText('Incluir abiertas/borradores') as HTMLInputElement).checked).toBe(true)
    expect(list.mock.calls[0][0]).not.toHaveProperty('statuses')
    fireEvent.change(selector, { target: { value: '2' } })
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ branch_id: 2, skip: 0 })))
    expect(getStats).toHaveBeenLastCalledWith({ start_date: hoy.inicio, end_date: hoy.fin, branch_id: 2 })
  })

  it('con una sola sucursal que vende (la otra es bodega) no hay selector ni columna', async () => {
    usuario('DUEÑO')
    getBranches.mockResolvedValue([SUC(1, 'Roma'), SUC(9, 'Bodega', false)])
    pintar()
    await screen.findByText('A-0041')
    await waitFor(() => expect(getBranches).toHaveBeenCalled())
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(cabeceras()).not.toContain('Sucursal')
  })

  it('el buscador filtra por folio o cliente sin volver al servidor', async () => {
    usuario('CAJERO', 1)
    list.mockResolvedValue({ items: [VENTA, { ...VENTA, id: 'venta-2', folio: 42, customer_name: 'Lupita' }], total: 2, page: 0, pages: 1 })
    pintar()
    await screen.findByText('A-0042')
    fireEvent.change(screen.getByLabelText('Buscar folio o cliente'), { target: { value: 'lupita' } })
    expect(screen.queryByText('A-0041')).toBeNull()
    expect(screen.getByText('A-0042')).toBeTruthy()
    expect(list).toHaveBeenCalledTimes(1)
  })

  it('una respuesta vieja no pisa a la nueva: si la primera llega tarde, la tabla muestra la de la sucursal elegida', async () => {
    usuario('ADMINISTRADOR')
    let resolverPrimera!: (v: unknown) => void
    list.mockReset()
      .mockImplementationOnce(() => new Promise((r) => { resolverPrimera = r }))
      .mockResolvedValue({ items: [{ ...VENTA, id: 'venta-c', folio: 77, branch_id: 2, branch_name: 'Condesa' }], total: 1, page: 0, pages: 1 })
    pintar()
    const selector = await screen.findByLabelText('Sucursal')
    fireEvent.change(selector, { target: { value: '2' } })
    await screen.findByText('A-0077')
    // Llega tarde la respuesta de toda la organización: se descarta.
    resolverPrimera({ items: [VENTA], total: 1, page: 0, pages: 1 })
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.getByText('A-0077')).toBeTruthy()
    expect(screen.queryByText('A-0041')).toBeNull()
  })

  it('el método OTHER se ve como «Otro»', async () => {
    usuario('CAJERO', 1)
    list.mockResolvedValue({ items: [{ ...VENTA, payments: [{ method: 'OTHER', amount: 250 }] }], total: 1, page: 0, pages: 1 })
    pintar()
    await screen.findByText('A-0041')
    expect(screen.getAllByText('Otro').length).toBeGreaterThan(0)
    expect(screen.queryByText('OTHER')).toBeNull()
  })

  it('si falla la lista muestra el error con Reintentar, no «Sin ventas»', async () => {
    usuario('CAJERO', 1)
    list.mockRejectedValueOnce({ response: { data: { detail: 'Sin conexión con el servidor' } } })
    pintar()
    const alerta = await screen.findByRole('alert')
    expect(alerta.textContent).toContain('Sin conexión con el servidor')
    expect(screen.queryByText('Sin ventas en este periodo')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Reintentar/ }))
    await screen.findByText('A-0041')
    expect(list).toHaveBeenCalledTimes(2)
  })

  it('si falla la lista en teléfono también muestra el error con Reintentar, no «Sin ventas»', async () => {
    telefono.valor = true
    usuario('CAJERO', 1)
    list.mockRejectedValueOnce({ response: { data: { detail: 'Sin conexión con el servidor' } } })
    pintar()
    const alerta = await screen.findByRole('alert')
    expect(alerta.textContent).toContain('Sin conexión con el servidor')
    expect(screen.queryByText('Sin ventas en este periodo')).toBeNull()
    expect(screen.queryAllByRole('columnheader')).toEqual([])
    fireEvent.click(screen.getByRole('button', { name: /Reintentar/ }))
    await screen.findByText('A-0041')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('el gerente no ve selector de sucursal, no pide sucursales y no manda branch_id (el backend lo confina)', async () => {
    usuario('GERENTE', 1)
    pintar()
    await screen.findByText('A-0041')
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(getBranches).not.toHaveBeenCalled()
    expect(list.mock.calls[0][0]).not.toHaveProperty('branch_id')
    expect(getStats.mock.calls[0][0]).not.toHaveProperty('branch_id')
    expect(cabeceras()).not.toContain('Sucursal')
  })

  it('la paginación pide la página siguiente (skip) y vuelve a la primera', async () => {
    usuario('CAJERO', 1)
    list.mockResolvedValue({ items: [VENTA], total: 250, page: 0, pages: 3 })
    pintar()
    await screen.findByText('A-0041')
    expect(screen.getByText(/Pág\. 1 \/ 3/)).toBeTruthy()
    expect((screen.getByRole('button', { name: /Anterior/ }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: /Siguiente/ }))
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 100 })))
    await screen.findByText(/Pág\. 2 \/ 3/)
    fireEvent.click(screen.getByRole('button', { name: /Anterior/ }))
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 0 })))
  })

  it('cambiar de preset pide el rango nuevo (en lista y estadísticas), vuelve a la página 0 y marca el preset', async () => {
    usuario('CAJERO', 1)
    list.mockResolvedValue({ items: [VENTA], total: 250, page: 0, pages: 3 })
    pintar()
    await screen.findByText('A-0041')
    fireEvent.click(screen.getByRole('button', { name: /Siguiente/ }))
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 100 })))
    fireEvent.click(screen.getByRole('button', { name: '7 días' }))
    const r = rangoPreset('7d')
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ start_date: r.inicio, end_date: r.fin, skip: 0 })))
    expect(getStats).toHaveBeenLastCalledWith({ start_date: r.inicio, end_date: r.fin })
    expect(screen.getByRole('button', { name: '7 días' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: 'Hoy' }).getAttribute('aria-pressed')).toBe('false')
  })

  it('Filtrar con una fecha vacía avisa y no llama al servidor; con rango invertido también avisa', async () => {
    usuario('CAJERO', 1)
    pintar()
    await screen.findByText('A-0041')
    const llamadas = list.mock.calls.length
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: /Filtrar/ }))
    expect(useToastStore.getState().toasts.map((t) => t.message)).toContain('Elige la fecha inicial y la final.')
    expect(list).toHaveBeenCalledTimes(llamadas)
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-10-20' } })
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-10-10' } })
    fireEvent.click(screen.getByRole('button', { name: /Filtrar/ }))
    expect(useToastStore.getState().toasts.map((t) => t.message)).toContain('La fecha inicial no puede ser mayor que la final.')
    expect(list).toHaveBeenCalledTimes(llamadas)
  })
})
