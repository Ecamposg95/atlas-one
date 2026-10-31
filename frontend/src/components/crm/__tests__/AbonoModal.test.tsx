// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

const { pay, getUnpaidDocuments } = vi.hoisted(() => ({ pay: vi.fn(), getUnpaidDocuments: vi.fn() }))
vi.mock('../../../api/customers', () => ({ customersApi: { pay, getUnpaidDocuments } }))

import { AbonoModal } from '../AbonoModal'

const RESPUESTA = {
  entries: [], customer_balance_before: 200, customer_balance_after: 50, unapplied: 0,
  applied: [{ sales_document_id: 'd1', folio: 'A-12', amount: 150, paid_in_full: true }],
  payment_id: 'pago-1', method: 'CASH', reference: null, received_at: '2026-10-31T18:00:00Z',
}
const TICKETS = [
  { id: 'd1', folio: 'A-12', created_at: '2026-10-01T18:00:00Z', total_amount: 100, paid_amount: 0, balance: 100, doc_type: 'ORDER' },
  { id: 'd2', folio: 'A-15', created_at: '2026-10-20T18:00:00Z', total_amount: 100, paid_amount: 0, balance: 100, doc_type: 'ORDER' },
]
const confirmar = () => screen.getByRole('button', { name: /Confirmar/ }) as HTMLButtonElement
const monto = () => screen.getByPlaceholderText('0.00')

beforeEach(() => { pay.mockReset().mockResolvedValue(RESPUESTA); getUnpaidDocuments.mockReset().mockResolvedValue(TICKETS) })
afterEach(cleanup)

describe('AbonoModal', () => {
  it('fuera de efectivo la referencia es obligatoria', async () => {
    render(<AbonoModal customerId={1} customerName="Ana" onClose={() => {}} />)
    fireEvent.change(monto(), { target: { value: '100' } })
    expect(confirmar().disabled).toBe(false)
    fireEvent.change(screen.getByLabelText('Método'), { target: { value: 'CARD' } })
    expect(confirmar().disabled).toBe(true)
    fireEvent.change(screen.getByLabelText(/Referencia/), { target: { value: '4421' } })
    expect(confirmar().disabled).toBe(false)
  })

  it('lista los tickets abiertos y manda el elegido; sin elegir, va del más viejo al más nuevo', async () => {
    const onDone = vi.fn(); const onClose = vi.fn()
    render(<AbonoModal customerId={1} customerName="Ana" onClose={onClose} onDone={onDone} />)
    const selector = await screen.findByLabelText('Aplicar a ticket')
    expect(screen.getByText(/A-15/)).toBeTruthy()
    fireEvent.change(monto(), { target: { value: '50' } })
    fireEvent.click(confirmar())
    await waitFor(() => expect(pay).toHaveBeenCalledWith(1, { amount: 50, method: 'CASH', reference: undefined, sales_document_id: undefined }))
    expect(onDone).toHaveBeenCalledWith(RESPUESTA)
    expect(onClose).toHaveBeenCalled()
    cleanup()
    render(<AbonoModal customerId={1} customerName="Ana" onClose={() => {}} />)
    fireEvent.change(await screen.findByLabelText('Aplicar a ticket'), { target: { value: 'd2' } })
    fireEvent.change(monto(), { target: { value: '20' } })
    fireEvent.click(confirmar())
    await waitFor(() => expect(pay).toHaveBeenLastCalledWith(1, expect.objectContaining({ sales_document_id: 'd2' })))
    void selector
  })

  it('muestra el detalle del backend cuando el abono se rechaza', async () => {
    pay.mockRejectedValueOnce({ response: { data: { detail: 'Debes abrir caja antes de cobrar en efectivo' } } })
    render(<AbonoModal customerId={1} customerName="Ana" onClose={() => {}} />)
    fireEvent.change(monto(), { target: { value: '10' } })
    fireEvent.click(confirmar())
    expect(await screen.findByText('Debes abrir caja antes de cobrar en efectivo')).toBeTruthy()
  })

  it('imprime el recibo al confirmar si la casilla está marcada', async () => {
    const imprimir = vi.fn(async () => {})
    render(<AbonoModal customerId={1} customerName="Ana" onClose={() => {}} imprimir={imprimir} />)
    const casilla = screen.getByLabelText('Imprimir recibo') as HTMLInputElement
    expect(casilla.checked).toBe(true)
    fireEvent.change(monto(), { target: { value: '10' } })
    fireEvent.click(confirmar())
    await waitFor(() => expect(imprimir).toHaveBeenCalledWith('pago-1'))
    cleanup()
    imprimir.mockClear()
    render(<AbonoModal customerId={1} customerName="Ana" onClose={() => {}} imprimir={imprimir} />)
    fireEvent.click(screen.getByLabelText('Imprimir recibo'))
    fireEvent.change(monto(), { target: { value: '10' } })
    fireEvent.click(confirmar())
    await waitFor(() => expect(pay).toHaveBeenCalled())
    expect(imprimir).not.toHaveBeenCalled()
  })

  it('si falla la impresión tras abonar, no deja reenviar el abono y permite reintentar solo el recibo', async () => {
    const imprimir = vi.fn().mockRejectedValueOnce(new Error('sin agente')).mockResolvedValue(undefined)
    const onDone = vi.fn(); const onClose = vi.fn()
    render(<AbonoModal customerId={1} customerName="Ana" onClose={onClose} onDone={onDone} imprimir={imprimir} />)
    fireEvent.change(monto(), { target: { value: '10' } })
    fireEvent.click(confirmar())
    expect(await screen.findByText('El abono quedó registrado, pero el recibo no se imprimió')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Confirmar/ })).toBeNull()
    expect(screen.queryByPlaceholderText('0.00')).toBeNull()
    expect(onDone).toHaveBeenCalledTimes(1)
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Reintentar impresión/ }))
    await waitFor(() => expect(imprimir).toHaveBeenCalledTimes(2))
    expect(imprimir).toHaveBeenNthCalledWith(2, 'pago-1')
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(pay).toHaveBeenCalledTimes(1)
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('un onDone que lanza no reabre el formulario ni reenvía el abono', async () => {
    const onDone = vi.fn(() => { throw new Error('el padre falló') })
    const onClose = vi.fn()
    render(<AbonoModal customerId={1} customerName="Ana" onClose={onClose} onDone={onDone} />)
    fireEvent.change(monto(), { target: { value: '10' } })
    fireEvent.click(confirmar())
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(pay).toHaveBeenCalledTimes(1)
    expect(onDone).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alert')).toBeNull()
    // El formulario no se rehabilita: el botón principal sigue en espera (spinner) y deshabilitado.
    expect((screen.getAllByRole('button').at(-1) as HTMLButtonElement).disabled).toBe(true)
  })

  it('con el abono en vuelo no se puede cancelar ni cerrar con Escape o el fondo', async () => {
    let resolver: (r: typeof RESPUESTA) => void = () => {}
    pay.mockReturnValueOnce(new Promise((res) => { resolver = res }))
    const onClose = vi.fn()
    render(<AbonoModal customerId={1} customerName="Ana" onClose={onClose} />)
    fireEvent.change(monto(), { target: { value: '10' } })
    fireEvent.click(confirmar())
    const cancelar = await screen.findByRole('button', { name: 'Cancelar' }) as HTMLButtonElement
    await waitFor(() => expect(cancelar.disabled).toBe(true))
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByRole('dialog'))
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(onClose).not.toHaveBeenCalled()
    resolver(RESPUESTA)
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('en efectivo no manda la referencia aunque se haya escrito antes de cambiar de método', async () => {
    render(<AbonoModal customerId={1} customerName="Ana" onClose={() => {}} />)
    fireEvent.change(monto(), { target: { value: '10' } })
    fireEvent.change(screen.getByLabelText('Método'), { target: { value: 'CARD' } })
    fireEvent.change(screen.getByLabelText(/Referencia/), { target: { value: '4421' } })
    fireEvent.change(screen.getByLabelText('Método'), { target: { value: 'CASH' } })
    fireEvent.click(confirmar())
    await waitFor(() => expect(pay).toHaveBeenCalledWith(1, { amount: 10, method: 'CASH', reference: undefined, sales_document_id: undefined }))
  })
})
