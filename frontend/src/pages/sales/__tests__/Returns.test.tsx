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

import { confirm } from '../../../components/ui/ConfirmDialog'
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

const abrirDetalle = async () => {
  await screen.findByText('DEV-000001')
  fireEvent.click(screen.getByLabelText('Ver detalle de DEV-000001'))
  return within(await screen.findByRole('dialog'))
}
const DETALLE_ALTO = { response: { data: { detail: 'Devolución en EFECTIVO de monto alto (12000) — confirma con force=True (umbral 10000).' } } }

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
    expect(list).toHaveBeenCalledWith({ status: 'PENDING', limit: 200 })
    expect(list).toHaveBeenCalledWith({ start_date: r30.inicio, end_date: r30.fin, limit: 200 })
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
    await waitFor(() => expect(list).toHaveBeenCalledWith({ branch_id: 2, status: 'PENDING', limit: 200 }))
    expect(list).toHaveBeenCalledWith({ branch_id: 2, start_date: r30.inicio, end_date: r30.fin, limit: 200 })
  })

  it('en Historial, el preset Hoy acota solo el historial; los pendientes se siguen pidiendo completos', async () => {
    usuario('GERENTE', 1)
    pintar()
    await screen.findByText('DEV-000001')
    fireEvent.click(screen.getByRole('button', { name: 'Historial' }))
    await screen.findByText('DEV-000002')
    fireEvent.click(screen.getByRole('button', { name: 'Hoy' }))
    await waitFor(() => expect(list).toHaveBeenLastCalledWith({ start_date: hoy.inicio, end_date: hoy.fin, limit: 200 }))
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
  it('tras aprobar recarga la lista y cierra el detalle', async () => {
    usuario('GERENTE', 1)
    pintar()
    const dialogo = await abrirDetalle()
    const antes = list.mock.calls.length
    fireEvent.click(dialogo.getByRole('button', { name: /Aprobar/ }))
    await waitFor(() => expect(approve).toHaveBeenCalledWith('dev-000001', false))
    await waitFor(() => expect(list.mock.calls.length).toBeGreaterThan(antes))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('efectivo alto: el backend pide force, se confirma con el diálogo de la app y se reintenta con force=true', async () => {
    usuario('GERENTE', 1)
    approve.mockReset().mockRejectedValueOnce(DETALLE_ALTO).mockResolvedValue(DEV('dev-000001', 'APPROVED'))
    vi.mocked(confirm).mockClear()
    pintar()
    const dialogo = await abrirDetalle()
    fireEvent.click(dialogo.getByRole('button', { name: /Aprobar/ }))
    await waitFor(() => expect(approve).toHaveBeenCalledWith('dev-000001', true))
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(approve).toHaveBeenCalledTimes(2)
    expect(approve).toHaveBeenNthCalledWith(1, 'dev-000001', false)
  })

  it('efectivo alto: si se cancela la confirmación no hay segundo approve', async () => {
    usuario('GERENTE', 1)
    approve.mockReset().mockRejectedValueOnce(DETALLE_ALTO)
    vi.mocked(confirm).mockClear()
    vi.mocked(confirm).mockResolvedValueOnce(false)
    pintar()
    const dialogo = await abrirDetalle()
    fireEvent.click(dialogo.getByRole('button', { name: /Aprobar/ }))
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1))
    await new Promise((r) => setTimeout(r, 20))
    expect(approve).toHaveBeenCalledTimes(1)
  })

  it('rechazar con motivo manda el motivo recortado', async () => {
    usuario('GERENTE', 1)
    reject.mockResolvedValue(DEV('dev-000001', 'PENDING'))
    pintar()
    const dialogo = await abrirDetalle()
    fireEvent.click(dialogo.getByRole('button', { name: /Rechazar/ }))
    fireEvent.change(await screen.findByLabelText(/Motivo \(opcional\)/), { target: { value: '  motivo  ' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirmar rechazo/ }))
    await waitFor(() => expect(reject).toHaveBeenCalledWith('dev-000001', 'motivo'))
  })

  it('rechazar sin motivo manda undefined', async () => {
    usuario('GERENTE', 1)
    reject.mockResolvedValue(DEV('dev-000001', 'PENDING'))
    pintar()
    const dialogo = await abrirDetalle()
    fireEvent.click(dialogo.getByRole('button', { name: /Rechazar/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Confirmar rechazo/ }))
    await waitFor(() => expect(reject).toHaveBeenCalledWith('dev-000001', undefined))
  })

  it('una fecha vacía no llega al backend', async () => {
    usuario('GERENTE', 1)
    pintar()
    await screen.findByText('DEV-000001')
    fireEvent.click(screen.getByRole('button', { name: 'Historial' }))
    const antes = list.mock.calls.length
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar' }))
    await new Promise((r) => setTimeout(r, 20))
    expect(list.mock.calls.length).toBe(antes)
  })
})
