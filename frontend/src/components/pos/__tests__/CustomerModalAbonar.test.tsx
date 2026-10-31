// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

const { getById, search } = vi.hoisted(() => ({ getById: vi.fn(), search: vi.fn() }))
vi.mock('../../../api/customers', () => ({ customersApi: { getById, search, create: vi.fn() } }))
const { getAbonoBase64, printViaAgent } = vi.hoisted(() => ({ getAbonoBase64: vi.fn(), printViaAgent: vi.fn() }))
vi.mock('../../../api/printer', () => ({ printerApi: { getAbonoBase64, printViaAgent } }))
// El mock expone `imprimir` para ejercitar lo que el POS le pasa al modal de abono.
vi.mock('../../crm/AbonoModal', () => ({
  AbonoModal: ({ imprimir }: { imprimir?: (id: string) => Promise<void> }) => (
    <button type="button" data-testid="abono-modal" onClick={() => { void imprimir?.('pago-1') }}>imprimir</button>
  ),
}))

import { CustomerModal } from '../modals/CustomerModal'
import { usePOSStore } from '../../../store/posStore'
import { toast } from '../../../store/toastStore'

beforeEach(() => {
  search.mockReset().mockResolvedValue([])
  getById.mockReset()
  getAbonoBase64.mockReset().mockResolvedValue('QUJD')
  printViaAgent.mockReset().mockResolvedValue(undefined)
  usePOSStore.setState({ customerId: 7, customerName: 'Ana Pérez', printerName: null })
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('CustomerModal: Abonar', () => {
  it('ofrece Abonar solo cuando el cliente elegido debe', async () => {
    getById.mockResolvedValue({ id: 7, name: 'Ana Pérez', current_balance: 250 })
    render(<CustomerModal onClose={() => {}} />)
    const boton = await screen.findByRole('button', { name: /Abonar/ })
    expect(screen.getByText(/Debe \$250\.00/)).toBeTruthy()
    fireEvent.click(boton)
    expect(await screen.findByTestId('abono-modal')).toBeTruthy()
  })

  it('sin impresora configurada avisa y ni siquiera pide el recibo', async () => {
    getById.mockResolvedValue({ id: 7, name: 'Ana Pérez', current_balance: 250 })
    const error = vi.spyOn(toast, 'error').mockImplementation(() => {})
    render(<CustomerModal onClose={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: /Abonar/ }))
    fireEvent.click(await screen.findByTestId('abono-modal'))
    await waitFor(() => expect(error).toHaveBeenCalledWith('Sin impresora configurada; el abono quedó registrado'))
    expect(getAbonoBase64).not.toHaveBeenCalled()
    expect(printViaAgent).not.toHaveBeenCalled()
  })

  it('con impresora pide el recibo y lo manda al agente', async () => {
    usePOSStore.setState({ printerName: 'EPSON' })
    getById.mockResolvedValue({ id: 7, name: 'Ana Pérez', current_balance: 250 })
    render(<CustomerModal onClose={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: /Abonar/ }))
    fireEvent.click(await screen.findByTestId('abono-modal'))
    await waitFor(() => expect(printViaAgent).toHaveBeenCalledWith('EPSON', 'QUJD'))
    expect(getAbonoBase64).toHaveBeenCalledWith('pago-1')
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
