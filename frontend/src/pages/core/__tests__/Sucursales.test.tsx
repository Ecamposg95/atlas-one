// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const { getBranches, createBranch, updateBranch, deleteBranch, commandCenterStats, dashboard } = vi.hoisted(() => ({
  getBranches: vi.fn(), createBranch: vi.fn(), updateBranch: vi.fn(), deleteBranch: vi.fn(),
  commandCenterStats: vi.fn(), dashboard: vi.fn(),
}))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches, createBranch, updateBranch, deleteBranch } }))
vi.mock('../../../api/reports', () => ({ reportsApi: { commandCenterStats, dashboard } }))

import { Sucursales, cambiosDeSucursal } from '../Sucursales'

const MATRIZ = { id: 1, name: 'Roma', branch_type: 'HQ', address: null, phone: null, is_headquarters: true, is_active: true, can_sell: true } as const
const SUCURSALES = [
  MATRIZ,
  { id: 2, name: 'Condesa', branch_type: 'STORE', address: 'Calle 1', phone: null, is_headquarters: false, is_active: true, can_sell: true },
]
const STATS = {
  global: {}, payment_methods: {}, hourly_distribution: [], alerts: [{ type: 'CRITICAL', msg: 'x', source: 'Roma', time: '' }], top_products: [],
  branches: [
    { id: 1, name: 'Roma', status: 'ONLINE', total_sales: 1000, pending_cuts: 0, pending_users: [], critical_stock: 1, is_hq: true },
    { id: 2, name: 'Condesa', status: 'OFFLINE', total_sales: 0, pending_cuts: 0, pending_users: [], critical_stock: 0, is_hq: false },
  ],
}
const DETALLE = {
  kpis: { sales: 1000, orders: 4, avg_ticket: 250, pending: 0, draft: 0, total_products: 0, transit_shipments: 0 },
  charts: { trend: { labels: [], data: [] }, hourly: { labels: [], data: [] }, payments: {} },
  top_products: [{ name: 'Blusa', qty: 3 }], low_stock: [{ name: 'Falda', sku: 'FAL', stock: 1 }],
  recent_sales: [{ folio: 'A-1', total: 250, time: '10:00', customer: '' }],
}
const pintar = (ruta = '/configuracion?tab=sucursales') => render(
  <MemoryRouter initialEntries={[ruta]}><Sucursales /></MemoryRouter>,
)

beforeEach(() => {
  getBranches.mockReset().mockResolvedValue(SUCURSALES)
  commandCenterStats.mockReset().mockResolvedValue(STATS)
  dashboard.mockReset().mockResolvedValue(DETALLE)
  createBranch.mockReset().mockResolvedValue({})
  updateBranch.mockReset().mockResolvedValue({})
})
afterEach(cleanup)

describe('Sucursales (pestaña de Configuración)', () => {
  it('sin sucursal en la URL: la rejilla con el estado de hoy y sin detalle', async () => {
    pintar()
    await screen.findByText('Roma')
    expect(screen.queryByTestId('detalle-sucursal')).toBeNull()
    expect(screen.getByText('Abierta')).toBeTruthy()
    expect(screen.getByText('Cerrada')).toBeTruthy()
    expect(dashboard).not.toHaveBeenCalled()
  })

  it('?sucursal=ID abre el detalle de hoy de esa sucursal (enlaces viejos de /hq/branches/:id)', async () => {
    pintar('/configuracion?tab=sucursales&sucursal=2')
    const detalle = await screen.findByTestId('detalle-sucursal')
    expect(detalle.textContent).toContain('Condesa')
    // La consulta del detalle sale después de pintar el panel: bajo carga (suite completa en CI) llega tarde.
    await waitFor(() => expect(dashboard).toHaveBeenCalledWith(expect.objectContaining({ branch_id: 2 })))
    expect(await screen.findByText('Blusa')).toBeTruthy()
  })

  it('tocar una sucursal abre su detalle y Cerrar lo quita', async () => {
    pintar()
    fireEvent.click(await screen.findByText('Roma'))
    expect(await screen.findByTestId('detalle-sucursal')).toBeTruthy()
    fireEvent.click(screen.getByText('Cerrar'))
    expect(screen.queryByTestId('detalle-sucursal')).toBeNull()
  })

  it('si las cifras de hoy fallan, la lista se sigue pudiendo administrar', async () => {
    commandCenterStats.mockRejectedValue(new Error('500'))
    pintar()
    expect(await screen.findByLabelText('Editar Condesa')).toBeTruthy()
  })

  it('editar el nombre de la matriz NO manda el tipo (le apagaba la venta)', async () => {
    pintar()
    fireEvent.click(await screen.findByLabelText('Editar Roma'))
    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Roma Norte' } })
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() => expect(updateBranch).toHaveBeenCalled())
    const [id, datos] = updateBranch.mock.calls[0]
    expect(id).toBe(1)
    expect(datos).toEqual({ name: 'Roma Norte', address: undefined, phone: undefined })
  })

  it('desactivar una sucursal manda solo is_active', async () => {
    pintar()
    fireEvent.click(await screen.findByLabelText('Editar Condesa'))
    fireEvent.click(screen.getByLabelText(/^Activa/))
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() => expect(updateBranch).toHaveBeenCalled())
    expect(updateBranch.mock.calls[0][1]).toMatchObject({ is_active: false })
    expect(updateBranch.mock.calls[0][1]).not.toHaveProperty('branch_type')
    expect(updateBranch.mock.calls[0][1]).not.toHaveProperty('can_sell')
  })

  it('el alta manda nombre y tipo', () => {
    expect(cambiosDeSucursal(null, { name: ' Sur ', branch_type: 'STORE', address: '', phone: '', can_sell: true, is_active: true }))
      .toEqual({ name: 'Sur', branch_type: 'STORE', address: undefined, phone: undefined })
  })
})
