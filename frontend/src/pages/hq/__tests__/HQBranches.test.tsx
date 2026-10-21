// frontend/src/pages/hq/__tests__/HQBranches.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

const { getBranches, commandCenterStats, dashboard } = vi.hoisted(() => ({
  getBranches: vi.fn(), commandCenterStats: vi.fn(), dashboard: vi.fn(),
}))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches } }))
vi.mock('../../../api/reports', () => ({ reportsApi: { commandCenterStats, dashboard } }))

import { HQBranches } from '../HQBranches'

const SUCURSALES = [
  { id: 1, name: 'Roma', branch_type: 'STORE', address: null, phone: null, is_headquarters: false, is_active: true },
  { id: 2, name: 'Condesa', branch_type: 'STORE', address: 'Calle 1', phone: null, is_headquarters: false, is_active: true },
]
const STATS = {
  global: {}, payment_methods: {}, hourly_distribution: [], alerts: [{ type: 'CRITICAL', msg: 'x', source: 'Roma', time: '' }], top_products: [],
  branches: [
    { id: 1, name: 'Roma', status: 'ONLINE', total_sales: 1000, pending_cuts: 0, pending_users: [], critical_stock: 1, is_hq: false },
    { id: 2, name: 'Condesa', status: 'OFFLINE', total_sales: 0, pending_cuts: 0, pending_users: [], critical_stock: 0, is_hq: false },
  ],
}
const DETALLE = {
  kpis: { sales: 1000, orders: 4, avg_ticket: 250, pending: 0, draft: 0, total_products: 0, transit_shipments: 0 },
  charts: { trend: { labels: [], data: [] }, hourly: { labels: [], data: [] }, payments: {} },
  top_products: [{ name: 'Blusa', qty: 3 }], low_stock: [{ name: 'Falda', sku: 'FAL', stock: 1 }],
  recent_sales: [{ folio: 'A-1', total: 250, time: '10:00', customer: '' }],
}
const pintar = (ruta: string) => render(
  <MemoryRouter initialEntries={[ruta]}>
    <Routes>
      <Route path="/hq/branches" element={<HQBranches />} />
      <Route path="/hq/branches/:branchId" element={<HQBranches />} />
    </Routes>
  </MemoryRouter>,
)

beforeEach(() => {
  getBranches.mockReset().mockResolvedValue(SUCURSALES)
  commandCenterStats.mockReset().mockResolvedValue(STATS)
  dashboard.mockReset().mockResolvedValue(DETALLE)
})
afterEach(cleanup)

describe('HQBranches (SP6)', () => {
  it('sin sucursal en la URL: solo la rejilla; "Abierta" sale del status del backend', async () => {
    pintar('/hq/branches')
    await screen.findByText('Roma')
    expect(screen.queryByTestId('detalle-sucursal')).toBeNull()
    expect(screen.getByText('Abierta')).toBeTruthy()
    expect(screen.getByText('Cerrada')).toBeTruthy()
    expect(dashboard).not.toHaveBeenCalled()
  })

  it('con :branchId pinta el detalle de hoy de esa sucursal en la misma pantalla', async () => {
    pintar('/hq/branches/2')
    const detalle = await screen.findByTestId('detalle-sucursal')
    expect(detalle.textContent).toContain('Condesa')
    expect(dashboard).toHaveBeenCalledWith(expect.objectContaining({ branch_id: 2 }))
    expect(await screen.findByText('Blusa')).toBeTruthy()
    expect(screen.getByText('A-1')).toBeTruthy()
  })

  it('tocar una tarjeta abre su detalle y Cerrar lo quita', async () => {
    pintar('/hq/branches')
    await screen.findByText('Roma')
    fireEvent.click(screen.getByText('Roma').closest('button')!)
    expect(await screen.findByTestId('detalle-sucursal')).toBeTruthy()
    fireEvent.click(screen.getByText('Cerrar'))
    expect(screen.queryByTestId('detalle-sucursal')).toBeNull()
  })
})
