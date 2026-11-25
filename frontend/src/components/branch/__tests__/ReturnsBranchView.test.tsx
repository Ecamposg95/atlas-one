// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

const { list, getById, listaDev } = vi.hoisted(() => ({ list: vi.fn(), getById: vi.fn(), listaDev: vi.fn() }))
vi.mock('../../../api/sales', () => ({ salesApi: { list, getById } }))
vi.mock('../../../api/returns', () => ({
  returnsApi: { list: listaDev },
  returnLabel: (r: { id: string }) => `DEV-${r.id.slice(-6).toUpperCase()}`,
}))
vi.mock('../../pos/modals/ReturnModal', () => ({
  ReturnModal: ({ initialSale }: { initialSale: { id: string } }) => <div data-testid="modal-devolucion">{initialSale.id}</div>,
}))

import { ReturnsBranchView } from '../ReturnsBranchView'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'

const usuario = (role: string) =>
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: 1, platform_role: 'NONE' } } as never)

const VENTA = { id: 'venta-1', series: 'A', folio: 12, status: 'PAID', total_amount: 250, created_at: '2026-11-20T15:00:00Z', customer_name: 'Mariana', payments: [], lines: [] }

beforeEach(() => {
  list.mockReset().mockResolvedValue({ items: [] })
  getById.mockReset().mockResolvedValue(VENTA)
  listaDev.mockReset().mockResolvedValue([])
  useEnabledModulesStore.setState({ diasVentasCaja: 30 })
})
afterEach(() => { cleanup(); useEnabledModulesStore.getState().reset() })

function buscar(texto: string) {
  render(<ReturnsBranchView />)
  const campo = screen.getByLabelText('Ticket a devolver')
  fireEvent.change(campo, { target: { value: texto } })
  fireEvent.keyDown(campo, { key: 'Enter' })
}

describe('ReturnsBranchView', () => {
  it('la cajera, ante un folio no encontrado, ve el plazo de su tienda', async () => {
    usuario('CAJERO')
    buscar('A-12')
    expect(await screen.findByText(/Solo aparecen ventas de tu sucursal de los últimos 30 días/)).toBeTruthy()
    expect(list).toHaveBeenCalledWith({ folio_search: 'A-12', limit: 10 })
  })

  it('con plazo 0 el aviso sigue siendo "solo ventas de hoy"', async () => {
    usuario('CAJERO')
    useEnabledModulesStore.setState({ diasVentasCaja: 0 })
    buscar('A-12')
    expect(await screen.findByText('Ticket no encontrado. Solo aparecen ventas de hoy; para días anteriores pide al gerente.')).toBeTruthy()
  })

  it('otro rol conserva el texto de siempre', async () => {
    usuario('GERENTE')
    buscar('A-12')
    expect(await screen.findByText('No encontré esa venta.')).toBeTruthy()
  })

  it('un folio escaneado que existe abre la devolución directo', async () => {
    usuario('CAJERO')
    list.mockResolvedValue({ items: [VENTA] })
    buscar('a-12')
    expect((await screen.findByTestId('modal-devolucion')).textContent).toBe('venta-1')
  })

  it('texto libre busca por cliente o producto y deja elegir', async () => {
    usuario('CAJERO')
    list.mockResolvedValue({ items: [VENTA] })
    buscar('mariana')
    fireEvent.click(await screen.findByText('A-0012'))
    expect(list).toHaveBeenCalledWith({ search: 'mariana', limit: 10 })
    expect(screen.getByTestId('modal-devolucion')).toBeTruthy()
  })

  it('lista las que esperan autorización y abre su ticket', async () => {
    usuario('CAJERO')
    listaDev.mockResolvedValue([{ id: 'r-abcdef', sale_id: 'venta-1', reason: 'Talla o medida', total_refunded: 250, sale: { id: 'venta-1', series: 'A', folio: 12 } }])
    render(<ReturnsBranchView />)
    fireEvent.click(await screen.findByRole('button', { name: /Autorizar/ }))
    expect(await screen.findByTestId('modal-devolucion')).toBeTruthy()
    expect(getById).toHaveBeenCalledWith('venta-1')
    expect(listaDev).toHaveBeenCalledWith({ status: 'PENDING', limit: 20 })
  })
})
