/** Tablero de plataforma: el día de UNA organización y la tira "Atención hoy".
 *  Espeja `app/schemas/platform_overview.py`. */

/** Global = la plataforma entera; Organización = un cliente a la vez. */
export type PlatformMode = 'global' | 'organizacion'

export interface OverviewMix {
  cash: number
  card: number
  transfer: number
  other: number
  cash_pct: number | null
  card_pct: number | null
  transfer_pct: number | null
  other_pct: number | null
}

export interface OverviewCash {
  status: 'OPEN' | 'CLOSED' | 'NONE'
  open_sessions: number
  open_hours: number | null
  last_close_at: string | null
  last_difference: number | null
  last_session_id: number | null
}

export interface OverviewReturns {
  pending_count: number
  pending_amount: number
  oldest_pending_days: number | null
  approved_today_count: number
  approved_today_amount: number
}

/** Una sucursal de la organización seleccionada. */
export interface BranchOverviewRow {
  id: number
  name: string
  org_id: number
  org_name: string
  sales_today: number
  sales_yesterday: number
  sales_same_weekday_last_week: number
  delta_yesterday_pct: number | null
  delta_last_week_pct: number | null
  tickets_today: number
  avg_ticket: number | null
  mix: OverviewMix
  cash: OverviewCash
  returns: OverviewReturns
  cancellations_today_count: number
  cancellations_today_amount: number
}

export interface OverviewTotals {
  units: number
  sales_today: number
  tickets_today: number
  avg_ticket: number | null
  open_sessions: number
  units_with_open_session: number
  returns_pending_count: number
  returns_pending_amount: number
  cancellations_today_count: number
  mix: OverviewMix
}

export interface OrgOverview {
  organization_id: number
  organization_name: string
  date: string
  generated_at: string
  totals: OverviewTotals
  rows: BranchOverviewRow[]
}

/** Un pendiente del día. `org_id`/`org_name` dicen de quién es: la tira cruza
 *  todas las organizaciones y nunca suma el dinero de dos. */
export interface AttentionItem {
  id: number
  name: string
  org_id: number
  org_name: string
  value: number | null
  detail: string
}

export type AttentionKey = 'no_cut' | 'cut_difference' | 'oldest_returns' | 'cancelled_today'

export type AttentionLists = Record<AttentionKey, AttentionItem[]>

export interface AttentionToday extends AttentionLists {
  date: string
  generated_at: string
}
