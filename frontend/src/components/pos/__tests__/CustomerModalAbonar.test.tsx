// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

const { getById, search } = vi.hoisted(() => ({ getById: vi.fn(), search: vi.fn() }))
vi.mock('../../../api/customers', () => ({ customersApi: { getById, search, create: vi.fn() } }))
vi.mock('../../../api/printer', () => ({ printerApi: { getAbonoBase64: vi.fn(), printViaAgent: vi.fn() } }))
vi.mock('../../crm/AbonoModal', () => ({ AbonoModal: () => <div data-testid="abono-modal" /> }))

import { CustomerModal } from '../modals/CustomerModal'
import { usePOSStore } from '../../../store/posStore'

beforeEach(() => {
  search.mockReset().mockResolvedValue([])
  getById.mockReset()
  usePOSStore.setState({ customerId: 7, customerName: 'Ana Pérez' })
})
afterEach(cleanup)

describe('CustomerModal: Abonar', () => {
  it('ofrece Abonar solo cuando el cliente elegido debe', async () => {
    getById.mockResolvedValue({ id: 7, name: 'Ana Pérez', current_balance: 250 })
    render(<CustomerModal onClose={() => {}} />)
    const boton = await screen.findByRole('button', { name: /Abonar/ })
    expect(screen.getByText(/Debe \$250\.00/)).toBeTruthy()
    fireEvent.click(boton)
    expect(await screen.findByTestId('abono-modal')).toBeTruthy()
  })

  it('sin deuda no hay botón', async () => {
    getById.mockResolvedValue({ id: 7, name: 'Ana Pérez', current_balance: 0 })
    render(<CustomerModal onClose={() => {}} />)
    await waitFor(() => expect(getById).toHaveBeenCalledWith(7))
    expect(screen.queryByRole('button', { name: /Abonar/ })).toBeNull()
  })

  it('con nombre libre (sin ficha) ni consulta ni botón', () => {
    usePOSStore.setState({ customerId: null, customerName: 'Cliente de paso' })
    render(<CustomerModal onClose={() => {}} />)
    expect(getById).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /Abonar/ })).toBeNull()
  })

  it('tocarSaldo sube la versión que el carrito observa', () => {
    const antes = usePOSStore.getState().saldoVersion
    usePOSStore.getState().tocarSaldo()
    expect(usePOSStore.getState().saldoVersion).toBe(antes + 1)
  })
})
