// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { Customers } from '../Customers'

vi.mock('../../../api/customers', async (orig) => ({
  ...(await orig<typeof import('../../../api/customers')>()),
  customersApi: {
    seguimiento: vi.fn().mockResolvedValue({ items: [], hoy: '2026-11-24' }),
    ficha: vi.fn().mockRejectedValue(new Error('sin ficha')),
    campos: vi.fn().mockResolvedValue([]),
    getAll: vi.fn().mockResolvedValue({ items: [{ id: 1, name: 'Ana', phone: null, tax_id: null, current_balance: 100, credit_limit: null }], total: 1 }),
    getStats: vi.fn().mockResolvedValue(null),
    getUnpaidDocuments: vi.fn().mockResolvedValue([]),
  },
}))

afterEach(cleanup)

describe('Customers: Registrar pago', () => {
  it('el monto recibe el foco al abrir el modal (el Modal enfoca primero cerrar)', async () => {
    const { container } = render(<Customers />)
    await waitFor(() => expect(container.querySelector('.fa-money-bill-wave')).not.toBeNull())
    fireEvent.click(container.querySelector('.fa-money-bill-wave')!.closest('button')!)
    const monto = await screen.findByPlaceholderText('0.00')
    await waitFor(() => expect(document.activeElement).toBe(monto))
  })
})
