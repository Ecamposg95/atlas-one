export interface DashboardUser {
  name: string
  branch_name: string
  role: string
}

export interface DashboardShift {
  is_open: boolean
  session_id?: number | null
  opened_at?: string | null
  duration_minutes?: number | null
}

export interface TopProduct {
  name: string
  units: string
}

export interface DashboardToday {
  /** null = la cajera con el turno abierto no recibe importes (conteo ciego). */
  sales_total: string | null
  sales_count: number
  avg_ticket: string | null
  returns_total: string | null
  returns_count: number
  goal?: string | null
  goal_progress_pct?: number | null
  payment_methods?: Record<string, string> | null
  top_products?: TopProduct[] | null
}

export type AlertKind = 'low_stock' | 'no_branch_price' | 'quote_expiring' | 'cash_variance'

export interface DashboardAlert {
  kind: AlertKind
  count?: number | null
  amount?: string | null
  deeplink: string
}

export interface BranchDashboard {
  user: DashboardUser
  shift: DashboardShift
  today: DashboardToday
  alerts: DashboardAlert[]
  closing_visible: boolean
}
