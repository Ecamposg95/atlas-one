// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { MixedPaymentModal } from '../modals/MixedPaymentModal'

afterEach(cleanup)

const pintar = (props: Partial<Parameters<typeof MixedPaymentModal>[0]> = {}) => {
  const onConfirm = vi.fn(async () => {})
  render(<MixedPaymentModal total={3000} onClose={() => {}} onConfirm={onConfirm} {...props} />)
  return onConfirm
}

const montoInput = () => screen.getByPlaceholderText('0.00') as HTMLInputElement

describe('Pago mixto con cliente: fiar', () => {
  it('sin cliente, un pago parcial no se puede cobrar', () => {
    pintar()
    fireEvent.change(montoInput(), { target: { value: '500' } })
    expect(screen.getByText('Pendiente')).toBeTruthy()
    expect((screen.getByText('Cobrar').closest('button') as HTMLButtonElement).disabled).toBe(true)
    expect(screen.queryByText('Todo a crédito')).toBeNull()
  })

  it('con cliente, lo que falta queda a crédito y se manda solo lo cobrado', async () => {
    const onConfirm = pintar({ customerId: 7, customerName: 'Ana Pérez' })
    fireEvent.change(montoInput(), { target: { value: '500' } })
    expect(screen.getByText('Queda a crédito')).toBeTruthy()
    expect(screen.getByText(/Ana Pérez/)).toBeTruthy()
    const boton = screen.getByText('Cobrar y fiar').closest('button') as HTMLButtonElement
    expect(boton.disabled).toBe(false)
    fireEvent.click(boton)
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1))
    expect(onConfirm).toHaveBeenCalledWith([{ method: 'CASH', amount: 500, reference: undefined }])
  })

  it('"Todo a crédito" manda la venta sin pagos', async () => {
    const onConfirm = pintar({ customerId: 7, customerName: 'Ana Pérez' })
    fireEvent.click(screen.getByText('Todo a crédito'))
    const boton = screen.getByText('Cobrar y fiar').closest('button') as HTMLButtonElement
    expect(boton.disabled).toBe(false)
    fireEvent.click(boton)
    await waitFor(() => expect(onConfirm).toHaveBeenCalledWith([]))
  })

  it('con cliente y pago completo, cobra normal', () => {
    pintar({ customerId: 7, customerName: 'Ana Pérez' })
    expect(screen.getByText('Exacto')).toBeTruthy()
    expect(screen.getByText('Cobrar')).toBeTruthy()
  })
})
