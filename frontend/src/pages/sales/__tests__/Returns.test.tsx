// frontend/src/pages/sales/__tests__/Returns.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react'

const { list, approve, reject, getBranches } = vi.hoisted(() => ({ list: vi.fn(), approve: vi.fn(), reject: vi.fn(), getBranches: vi.fn() }))
vi.mock('../../../api/returns', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/returns')>()),
  returnsApi: { list, approve, reject },
}))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches } }))
vi.mock('../../../components/branch/ReturnsBranchView', () => ({ ReturnsBranchView: () => <div data-testid="asistente-cajera" /> }))
vi.mock('../../../components/ui/ConfirmDialog', () => ({ confirm: vi.fn(async () => true) }))

import { Returns } from '../Returns'
import { useAuthStore } from '../../../store/authStore'
import { rangoPreset } from '../../reports/presetsReportes'

const r30 = rangoPreset('30d')
const hoy = rangoPreset('hoy')
const DEV = (id: string, status: 'PENDING' | 'APPROVED') => ({
  id, sale_id: 's1', reason: 'Talla equivocada', total_refunded: 300, refund_method: 'CASH', status,
  branch_id: 1, branch: { id: 1, name: 'Roma' }, user: { id: 2, username: 'mirna', full_name: 'Mirna' }, supervisor: null,
  created_at: '2026-10-20T15:00:00Z',
  items: [{ id: 'i1', return_id: id, variant_id: 'v1', quantity: 1, refund_amount: 300, is_inventory_reentry: true, variant: { id: 'v1', sku: 'BLU', product_name: 'Blusa' } }],
})
const SUC = (id: number, name: string, can_sell = true) =>
  ({ id, name, branch_type: 'STORE', address: null, phone: null, is_headquarters: false, is_active: true, can_sell })
const usuario = (role: string, branch_id: number | null = null) =>
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id, platform_role: 'NONE' } } as never)
const pintar = () => render(<MemoryRouter><Returns /></MemoryRouter>)
const llamadasPendientes = () => list.mock.calls.filter(([p]) => (p as { status?: string } | undefined)?.status === 'PENDING')

beforeEach(() => {
  list.mockReset().mockImplementation(async (p?: { status?: string }) =>
    (p?.status === 'PENDING' ? [DEV('dev-000001', 'PENDING')] : [DEV('dev-000001', 'PENDING'), DEV('dev-000002', 'APPROVED')]))
  approve.mockReset().mockResolvedValue(DEV('dev-000001', 'APPROVED'))
  reject.mockReset()
  getBranches.mockReset().mockResolvedValue([SUC(1, 'Roma'), SUC(2, 'Condesa')])
})
afterEach(cleanup)

describe('Devoluciones (/returns, fusión de HQReturns)', () => {
  it('la cajera ve el asistente de sucursal, no la bandeja', () => {
    usuario('CAJERO', 1)
    pintar()
    expect(screen.getByTestId('asistente-cajera')).toBeTruthy()
    expect(list).not.toHaveBeenCalled()
  })

  it('el gerente ve la bandeja sin selector pero con columna Sucursal (recibe toda la org): pendientes sin fechas, historial en 30 días, estados en español, y aprueba', async () => {
    usuario('GERENTE', 1)
    pintar()
    await screen.findByText('DEV-000001')
    expect(getBranches).not.toHaveBeenCalled()
    expect(list).toHaveBeenCalledWith({ status: 'PENDING' })
    expect(list).toHaveBeenCalledWith({ start_date: r30.inicio, end_date: r30.fin })
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent)).toContain('Sucursal')
    expect(screen.getByText('Roma')).toBeTruthy()
    expect(screen.getByText('Por aprobar')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Ver detalle de DEV-000001'))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: /Aprobar/ }))
    await waitFor(() => expect(approve).toHaveBeenCalledWith('dev-000001', false))
  })

  it('la administradora con dos sucursales que venden ve el selector y la columna; al elegir, pendientes e historial llevan branch_id', async () => {
    usuario('ADMINISTRADOR')
    pintar()
    await screen.findByText('DEV-000001')
    const selector = await screen.findByLabelText('Sucursal')
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent)).toContain('Sucursal')
    fireEvent.change(selector, { target: { value: '2' } })
    await waitFor(() => expect(list).toHaveBeenCalledWith({ branch_id: 2, status: 'PENDING' }))
    expect(list).toHaveBeenCalledWith({ branch_id: 2, start_date: r30.inicio, end_date: r30.fin })
  })

  it('en Historial, el preset Hoy acota solo el historial; los pendientes se siguen pidiendo completos', async () => {
    usuario('GERENTE', 1)
    pintar()
    await screen.findByText('DEV-000001')
    fireEvent.click(screen.getByRole('button', { name: 'Historial' }))
    await screen.findByText('DEV-000002')
    fireEvent.click(screen.getByRole('button', { name: 'Hoy' }))
    await waitFor(() => expect(list).toHaveBeenLastCalledWith({ start_date: hoy.inicio, end_date: hoy.fin }))
    expect(llamadasPendientes().length).toBeGreaterThanOrEqual(2)
    for (const [p] of llamadasPendientes()) expect(p).not.toHaveProperty('start_date')
  })
  it('una respuesta vieja no pisa a la nueva: si la primera llega tarde, la bandeja muestra la de la sucursal elegida', async () => {
    usuario('ADMINISTRADOR')
    const tardias: Array<(v: unknown) => void> = []
    list.mockReset()
      .mockImplementationOnce(() => new Promise((r) => { tardias.push(r) })) // pendientes de toda la org
      .mockImplementationOnce(() => new Promise((r) => { tardias.push(r) })) // historial de toda la org
      .mockImplementation(async (p?: { status?: string }) =>
        (p?.status === 'PENDING' ? [DEV('dev-000077', 'PENDING')] : []))
    pintar()
    const selector = await screen.findByLabelText('Sucursal')
    fireEvent.change(selector, { target: { value: '2' } })
    await screen.findByText('DEV-000077')
    // Llega tarde la respuesta de toda la organización: se descarta.
    tardias[0]([DEV('dev-000001', 'PENDING')])
    tardias[1]([])
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.getByText('DEV-000077')).toBeTruthy()
    expect(screen.queryByText('DEV-000001')).toBeNull()
  })

  it('si falla la carga muestra el error con Reintentar, no «No hay devoluciones pendientes»', async () => {
    usuario('GERENTE', 1)
    list.mockReset().mockRejectedValueOnce({ response: { data: { detail: 'Sin conexión con el servidor' } } })
      .mockImplementation(async (p?: { status?: string }) =>
        (p?.status === 'PENDING' ? [DEV('dev-000001', 'PENDING')] : []))
    pintar()
    const alerta = await screen.findByRole('alert')
    expect(alerta.textContent).toContain('Sin conexión con el servidor')
    expect(screen.queryByText('No hay devoluciones pendientes')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Reintentar/ }))
    await screen.findByText('DEV-000001')
  })
})
