// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const { list, create } = vi.hoisted(() => ({ list: vi.fn(), create: vi.fn() }))
vi.mock('../../../../hooks/useIsMobile', () => ({ useEsTelefono: () => false }))
vi.mock('../../../../api/sales', () => ({ salesApi: { list } }))
vi.mock('../../../../api/returns', () => ({ returnsApi: { create } }))

import { ReturnModal } from '../ReturnModal'
import { useAuthStore } from '../../../../store/authStore'

const usuario = (role: string) =>
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: 1, platform_role: 'NONE' } } as never)

const VENTA = {
  id: 'venta-1', series: 'A', folio: 41, status: 'PAID', total_amount: 250, created_at: '2026-10-20T15:00:00Z',
  payments: [{ method: 'CASH', amount: 250 }],
  lines: [{ variant_id: 'v1', description: 'Blusa', sku: 'BLU', quantity: 1, unit_price: '250' }],
}

beforeEach(() => {
  list.mockReset().mockResolvedValue({ items: [] })
  create.mockReset()
})
afterEach(cleanup)

async function buscarFolio() {
  render(<ModalWrap />)
  fireEvent.click(screen.getByRole('button', { name: /Por folio/ }))
  fireEvent.change(screen.getByPlaceholderText(/Folio del ticket/), { target: { value: 'A-1' } })
  fireEvent.keyDown(screen.getByPlaceholderText(/Folio del ticket/), { key: 'Enter' })
}
const ModalWrap = () => <ReturnModal onClose={() => {}} onSuccess={() => {}} />

describe('ReturnModal', () => {
  it('la cajera, ante un folio no encontrado, ve que solo aparecen ventas de hoy', async () => {
    usuario('CAJERO')
    await buscarFolio()
    expect(await screen.findByText('Ticket no encontrado. Solo aparecen ventas de hoy; para días anteriores pide al gerente.')).toBeTruthy()
  })

  it('el gerente sigue viendo solo "Ticket no encontrado"', async () => {
    usuario('GERENTE')
    await buscarFolio()
    expect(await screen.findByText('Ticket no encontrado')).toBeTruthy()
  })

  it('un 403 del backend al registrar muestra su detail tal cual', async () => {
    usuario('CAJERO')
    const detail = 'Solo puedes devolver ventas de hoy. Para días anteriores pide al gerente.'
    create.mockRejectedValue({ response: { status: 403, data: { detail } } })
    render(<ReturnModal onClose={() => {}} onSuccess={() => {}} initialSale={VENTA as never} />)
    fireEvent.click(screen.getByText('Todas (1)'))
    fireEvent.change(screen.getByPlaceholderText(/Producto defectuoso/), { target: { value: 'Talla' } })
    fireEvent.click(screen.getByRole('button', { name: /Registrar/ }))
    expect(await screen.findByText(detail)).toBeTruthy()
  })
})
