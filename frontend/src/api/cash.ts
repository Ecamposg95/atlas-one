import client from './client'
import type { CashSession } from '../types/cash'

export interface CashSummary {
  session_id: number
  opening_amount: number
  expected_cash: number
  total_sales: number
  /** Lo que quedó fiado a clientes en las ventas del turno (spec 2026-10-29 §2.3). */
  credit_sales: number
  /** Abonos a cuenta cobrados en el turno; ya están dentro de los totales por método. */
  customer_payments: number
  total_cash: number
  total_card: number
  total_transfer: number
  total_inflows: number
  total_outflows: number
  cash_refunds: number
  returns_count: number
  returns_total: number
  movements: CashMovementRecord[]
}

export interface CashMovementRecord {
  id: number
  type: 'IN' | 'OUT'
  amount: number
  concept: string
  created_at: string
}

/** Un cajero dentro del corte global de la sucursal. */
export interface CorteDeCajero {
  session_id: number
  user_id: number
  username: string
  full_name: string | null
  status: 'OPEN' | 'CLOSED'
  opened_at: string | null
  closed_at: string | null
  opening_balance: number
  closing_balance: number
  /** Diferencia recalculada en vivo por el backend, no la persistida. */
  difference: number
  /** Efectivo esperado — sale de `compute_expected_cash`, fuente única. */
  expected_cash: number
  sales: number
  tickets: number
  cash: number
  card: number
  transfer: number
  change_given: number
  inflows: number
  outflows: number
  cash_refunds: number
  returns_count: number
}

/**
 * Respuesta de `GET /api/cash/branch-summary`: consolida TODAS las sesiones de
 * una sucursal en una fecha, no solo la del usuario que pregunta. Es el
 * endpoint del back-office (ADMINISTRADOR/DUEÑO/GERENTE); `/cash/status` es el
 * del cajero y solo devuelve la sesión abierta propia.
 */
export interface CorteDeSucursal {
  branch_id: number
  branch_name: string
  date: string
  sessions_count: number
  cashiers: CorteDeCajero[]
  totals: {
    sales: number
    tickets: number
    cash: number
    card: number
    transfer: number
    inflows: number
    outflows: number
    cash_refunds: number
    opening_total: number
    closing_total: number
    difference_total: number
  }
}

export const cashApi = {
  getStatus: async (): Promise<CashSession | null> => {
    const { data } = await client.get<CashSession | null>('/cash/status')
    return data
  },

  /** Corte global de una sucursal para una fecha (YYYY-MM-DD). */
  branchSummary: async (branchId: number, date?: string): Promise<CorteDeSucursal> => {
    const { data } = await client.get<CorteDeSucursal>('/cash/branch-summary', {
      params: date ? { branch_id: branchId, date } : { branch_id: branchId },
    })
    return data
  },

  getSummary: async (sessionId?: number): Promise<CashSummary> => {
    const { data } = await client.get<any>('/cash/summary', {
      params: sessionId != null ? { session_id: sessionId } : undefined,
    })
    // Backend returns a nested structure; flatten it for component use
    const today = new Date().toLocaleDateString('en-CA')
    return {
      session_id: data?.session?.id ?? 0,
      opening_amount: data?.session?.opening_balance ?? 0,
      expected_cash: data?.expected?.cash_physical ?? 0,
      total_sales: data?.kpis?.total_sales ?? 0,
      credit_sales: data?.kpis?.credit_sales ?? 0,
      customer_payments: data?.kpis?.customer_payments ?? 0,
      total_cash: data?.payments?.cash?.total ?? 0,
      total_card: data?.payments?.card?.total ?? 0,
      total_transfer: data?.payments?.transfer?.total ?? 0,
      total_inflows: data?.movements?.inflows ?? 0,
      total_outflows: data?.movements?.outflows ?? 0,
      cash_refunds: data?.returns?.cash_refunds ?? 0,
      returns_count: data?.returns?.count ?? 0,
      returns_total: data?.returns?.total ?? 0,
      movements: (data?.movements?.list ?? []).map((m: any, i: number) => ({
        id: i,
        type: m.type as 'IN' | 'OUT',
        amount: m.amount ?? 0,
        concept: m.reason ?? '',
        created_at: `${today}T${m.time ?? '00:00'}:00`,
      })),
    }
  },

  history: async (skip = 0, limit = 50): Promise<CashSession[]> => {
    const { data } = await client.get<CashSession[]>('/cash/history', {
      params: { skip, limit },
    })
    return Array.isArray(data) ? data : (data as any)?.items ?? []
  },

  open: async (opening_balance: number, notes?: string): Promise<CashSession> => {
    const { data } = await client.post<CashSession>('/cash/open', { opening_balance, notes })
    return data
  },

  close: async (closing_balance: number, notes?: string): Promise<CashSession> => {
    const { data } = await client.post<CashSession>('/cash/close', { closing_balance, notes })
    return data
  },

  inflow: async (amount: number, concept: string): Promise<void> => {
    await client.post('/cash/inflow', null, { params: { amount, reason: concept } })
  },

  outflow: async (amount: number, concept: string): Promise<void> => {
    await client.post('/cash/outflow', null, { params: { amount, reason: concept } })
  },

  getPdf: async (sessionId: number): Promise<Blob> => {
    const { data } = await client.get<Blob>(`/cash/${sessionId}/pdf`, { responseType: 'blob' })
    return data
  },
}
