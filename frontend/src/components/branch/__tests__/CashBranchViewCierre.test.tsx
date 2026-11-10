// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, act } from '@testing-library/react'

// Estado del servidor simulado: el turno abierto deja de existir tras cerrar.
let turnoAbierto: Record<string, unknown> | null = null
const get = vi.fn(async (url: string) => {
  if (url === '/cash/status') return { data: turnoAbierto }
  return { data: [] }
})
vi.mock('../../../api/client', () => ({ default: { get: (url: string) => get(url) } }))

const close = vi.fn(async () => {
  turnoAbierto = null
  return { id: 7, difference: '-50', warnings: [] }
})
vi.mock('../../../api/cash', () => ({
  cashApi: {
    getSummary: vi.fn(async () => ({
      opening_amount: 500, total_cash: 600, total_card: 0, total_transfer: 0,
      total_inflows: 0, total_outflows: 0, cash_refunds: 0, returns_count: 0,
      expected_cash: 1050, total_sales: 600, credit_sales: 0, customer_payments: 0,
      movements: [],
    })),
    close: (...args: unknown[]) => close(...(args as [])),
  },
}))
vi.mock('../../../api/printer', () => ({ printerApi: { printCashCut: vi.fn(), getCashCutBase64: vi.fn() } }))

import { CashBranchView } from '../CashBranchView'

const statusCalls = () => get.mock.calls.filter(([u]) => u === '/cash/status').length

beforeEach(() => {
  turnoAbierto = {
    id: 7, opened_at: new Date().toISOString(), closed_at: null,
    opening_balance: '500', closing_balance: null, total_cash_sales: '0', difference: '0',
  }
  get.mockClear()
  Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
})
afterEach(cleanup)

describe('CashBranchView: el resultado del corte sobrevive al refresco en vivo', () => {
  it('foco/visibilidad no desmontan el resultado y "Listo" lo quita', async () => {
    render(<CashBranchView />)
    // Botón grande "Cerrar turno" de la banda de acciones.
    const abrir = await screen.findByRole('button', { name: /Cerrar turno/ })
    fireEvent.click(abrir)

    const input = await screen.findByRole('spinbutton')
    fireEvent.change(input, { target: { value: '1000' } })
    const botones = screen.getAllByRole('button', { name: /Cerrar turno/ })
    fireEvent.click(botones[botones.length - 1])

    await screen.findByRole('heading', { name: 'Turno cerrado' })
    const antes = statusCalls()

    // El servidor ya no tiene turno: un refresco vaciaría `current`.
    await act(async () => {
      window.dispatchEvent(new Event('focus'))
      document.dispatchEvent(new Event('visibilitychange'))
    })

    expect(statusCalls()).toBe(antes)
    expect(screen.getByRole('heading', { name: 'Turno cerrado' })).toBeTruthy()
    expect(screen.getByText('Esperado en caja')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Listo' }))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Turno cerrado' })).toBeNull())
    expect(statusCalls()).toBeGreaterThan(antes)
  })
})
