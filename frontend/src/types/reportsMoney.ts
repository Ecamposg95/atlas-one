// Types for Platform Reports Money module
// Cash cuts, returns, cancellations, and payment methods biweekly reports

export type MoneyTab = 'cortes' | 'devoluciones' | 'cancelaciones' | 'quincenal'
export type CompareMode = 'none' | 'prev' | 'yoy'
export type BiweeklyUnit = 'branch' | 'org'

export interface CashCutRow {
  branch_id: number
  name: string
  org_id: number | null
  org_name: string
  sessions_closed: number
  sessions_with_difference: number
  shortage_total: string
  overage_total: string
  avg_abs_difference: string
  sessions_open_unclosed: number
}

export interface CashCutSession {
  session_id: number
  cashier: string
  opened_at: string | null
  closed_at: string | null
  expected: string
  reported: string
  difference: string
}

export interface CashCutCashier {
  user_id: number
  full_name: string
  sessions: number
  shortage_total: string
  overage_total: string
}

export interface CashCutDetail {
  branch_id: number
  branch_name: string
  by_cashier: CashCutCashier[]
  sessions: CashCutSession[]
  total: number
  offset: number
  limit: number
}

export interface ReturnsRow {
  branch_id: number
  name: string
  org_id: number | null
  org_name: string
  pending_count: number
  pending_amount: string
  approved_count: number
  approved_amount: string
  rejected_count: number
  by_method: {
    cash: string
    card: string
    transfer: string
    other: string
  }
  avg_hours_to_approve: string | null
  top_reasons: string[]
}

export interface ReturnDetailRow {
  return_id: string
  folio: string
  created_at: string | null
  approved_at: string | null
  status: string
  method: string
  amount: string
  reason: string
  cashier: string
}

export interface ReturnsDetail {
  branch_id: number
  branch_name: string
  items: ReturnDetailRow[]
  total: number
  offset: number
  limit: number
}

export interface CancellationsRow {
  branch_id: number
  name: string
  org_id: number | null
  org_name: string
  count: number
  amount: string
  by_user: Array<{
    user_id: number | null
    full_name: string
    count: number
    amount: string
  }>
  top_reasons: string[]
}

export interface CancellationDetailRow {
  event_id: number
  ts: string | null
  sale_id: string | null
  folio: string
  amount: string
  user: string
  reason: string
  prev_status: string
}

export interface CancellationsDetail {
  branch_id: number
  branch_name: string
  items: CancellationDetailRow[]
  total: number
  offset: number
  limit: number
}

export interface BiweeklyRow {
  period: string
  period_label: string
  unit_id: number
  name: string
  org_name: string
  cash_net: string
  card: string
  transfer: string
  other: string
  total: string
  tickets: number
}
