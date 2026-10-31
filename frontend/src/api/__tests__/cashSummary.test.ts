import { describe, it, expect, vi } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../client', () => ({ default: { get } }))

import { cashApi } from '../cash'

describe('cashApi.getSummary', () => {
  it('aplana fiado y abonos del corte (0 si el backend no los manda)', async () => {
    get.mockResolvedValueOnce({ data: { session: { id: 3 }, kpis: { total_sales: 100, credit_sales: 60, customer_payments: 30 }, payments: {}, movements: {}, returns: {}, expected: {} } })
    const s = await cashApi.getSummary(3)
    expect(s.total_sales).toBe(100)
    expect(s.credit_sales).toBe(60)
    expect(s.customer_payments).toBe(30)
    get.mockResolvedValueOnce({ data: { session: { id: 4 }, kpis: { total_sales: 10 } } })
    const viejo = await cashApi.getSummary(4)
    expect(viejo.credit_sales).toBe(0)
    expect(viejo.customer_payments).toBe(0)
  })
})
