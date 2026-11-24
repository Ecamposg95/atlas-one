// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { CockpitDayKPIs } from '../CockpitDayKPIs'
import { BLIND_MASK } from '../../../utils/blindCash'
import type { DashboardToday } from '../../../types/branchDashboard'

// Con el turno abierto el servidor ya no manda importes a la cajera
// (2026-11-17): el desglose llega en null y se enmascara entero, sin $0.
const ciego: DashboardToday = {
  sales_total: null, sales_count: 3, avg_ticket: null, returns_total: null, returns_count: 0,
  goal: null, goal_progress_pct: null, payment_methods: null, top_products: [],
}

describe('Mi día de la cajera sin importes del turno', () => {
  afterEach(cleanup)

  it('enmascara efectivo, tarjeta y transferencia cuando no llega desglose', () => {
    render(<CockpitDayKPIs.PaymentMethods today={ciego} shiftOpen />)
    expect(screen.getAllByText(BLIND_MASK)).toHaveLength(3)
    expect(screen.queryByText(/\$0/)).toBeNull()
  })

  it('con desglose, solo el efectivo va ciego', () => {
    render(<CockpitDayKPIs.PaymentMethods today={{ ...ciego, payment_methods: { CASH: '100', CARD: '50' } }} shiftOpen />)
    expect(screen.getAllByText(BLIND_MASK)).toHaveLength(1)
  })
})
