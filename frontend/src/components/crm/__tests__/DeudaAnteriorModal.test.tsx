// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

const { cargarDeudaAnterior } = vi.hoisted(() => ({ cargarDeudaAnterior: vi.fn() }))
vi.mock('../../../api/customers', () => ({ customersApi: { cargarDeudaAnterior } }))

import { DeudaAnteriorModal, hoyMx } from '../DeudaAnteriorModal'

const guardar = () => screen.getByRole('button', { name: /Guardar/ }) as HTMLButtonElement

beforeEach(() => { cargarDeudaAnterior.mockReset().mockResolvedValue({ entry: null, customer_balance: 1500 }) })
afterEach(cleanup)

describe('DeudaAnteriorModal', () => {
  it('manda monto, fecha y nota, y avisa al terminar', async () => {
    const onDone = vi.fn(); const onClose = vi.fn()
    render(<DeudaAnteriorModal customerId={7} customerName="Ana" onClose={onClose} onDone={onDone} />)
    expect(guardar().disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Cuánto debe'), { target: { value: '1500' } })
    fireEvent.change(screen.getByLabelText('Desde cuándo'), { target: { value: '2026-08-15' } })
    fireEvent.change(screen.getByLabelText(/Nota/), { target: { value: '  libreta  ' } })
    fireEvent.click(guardar())
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(cargarDeudaAnterior).toHaveBeenCalledWith(7, { amount: 1500, fecha: '2026-08-15', nota: 'libreta' })
    expect(onDone).toHaveBeenCalledWith({ entry: null, customer_balance: 1500 })
  })

  it('arranca con la fecha de hoy y no acepta una fecha futura', () => {
    render(<DeudaAnteriorModal customerId={7} customerName="Ana" onClose={() => {}} />)
    const fecha = screen.getByLabelText('Desde cuándo') as HTMLInputElement
    expect(fecha.value).toBe(hoyMx())
    fireEvent.change(screen.getByLabelText('Cuánto debe'), { target: { value: '100' } })
    expect(guardar().disabled).toBe(false)
    fireEvent.change(fecha, { target: { value: '2999-01-01' } })
    expect(guardar().disabled).toBe(true)
  })

  it('muestra el error del servidor y deja reintentar', async () => {
    cargarDeudaAnterior.mockRejectedValueOnce({ response: { data: { detail: 'La fecha de la deuda no puede estar en el futuro' } } })
    const onClose = vi.fn()
    render(<DeudaAnteriorModal customerId={7} customerName="Ana" onClose={onClose} />)
    fireEvent.change(screen.getByLabelText('Cuánto debe'), { target: { value: '100' } })
    fireEvent.click(guardar())
    expect((await screen.findByRole('alert')).textContent).toMatch(/futuro/)
    expect(onClose).not.toHaveBeenCalled()
    expect(guardar().disabled).toBe(false)
  })
})
