// Types for Platform Reports module (F4 — 2026-04-30)
// Mirrors the response shapes from /api/platform/reports/* endpoints.

import type { CompareMode } from './reportsMoney'

export type ReportTab =
  | 'productos' | 'sucursales' | 'vendedores' | 'clientes'
  | 'cortes' | 'devoluciones' | 'cancelaciones' | 'quincenal'

export interface ReportFilters {
  range?: '7d' | '30d' | '90d' | '12m' | 'custom'
  start?: string  // ISO date
  end?: string    // ISO date
  org_id?: number
  branch_id?: number
}

export interface ReportParams extends ReportFilters {
  limit?: number   // default 100, max 500
  offset?: number
  sort?: string    // e.g. "revenue:desc"
  compare?: CompareMode
}

export interface PaginatedReport<T> {
  items: T[]
  total: number
  offset: number
  limit: number
}

// ── Pivot row shapes ────────────────────────────────────────────────────────

export interface ProductRow {
  product_id: string
  sku: string
  name: string
  brand: string | null
  department: string | null
  units_sold: number
  revenue: string                        // Decimal as string
  aov: string
  return_rate_pct: string
  estimated_margin_pct: string | null
  // Presentes solo cuando la petición llevó `compare !== 'none'`.
  // El dinero llega como cadena con dos decimales; los conteos, como números.
  prev_revenue?: string
  delta_revenue_pct?: number | null
  prev_units_sold?: number
  delta_units_sold_pct?: number | null
  prev_aov?: string
  delta_aov_pct?: number | null
}

export interface BranchRow {
  branch_id: number
  name: string
  org_id: number
  org_name: string
  city: string | null
  transactions: number
  revenue: string
  avg_ticket: string
  active_cashiers: number
  return_rate_pct: string
  // Presentes solo cuando la petición llevó `compare !== 'none'`.
  prev_revenue?: string
  delta_revenue_pct?: number | null
  prev_transactions?: number
  delta_transactions_pct?: number | null
  prev_avg_ticket?: string
  delta_avg_ticket_pct?: number | null
}

export interface SellerRow {
  user_id: number
  full_name: string
  role: string
  branch_id: number
  branch_name: string
  org_id: number
  org_name: string
  transactions: number
  revenue: string
  avg_ticket: string
  active_days: number
  // Presentes solo cuando la petición llevó `compare !== 'none'`.
  prev_revenue?: string
  delta_revenue_pct?: number | null
  prev_transactions?: number
  delta_transactions_pct?: number | null
  prev_avg_ticket?: string
  delta_avg_ticket_pct?: number | null
}

export interface CustomerRow {
  customer_id: number
  customer_name: string
  ticket_count: number
  total_revenue: string
  avg_ticket: string
  last_purchase: string                  // ISO datetime
  avg_days_between_purchases: number | null
  // Presentes solo cuando la petición llevó `compare !== 'none'`.
  prev_total_revenue?: string
  delta_total_revenue_pct?: number | null
  prev_ticket_count?: number
  delta_ticket_count_pct?: number | null
  prev_avg_ticket?: string
  delta_avg_ticket_pct?: number | null
}

// ── Drill-down detail shapes ────────────────────────────────────────────────

export interface ProductDetailRow {
  document_id: string
  folio: number
  series: string
  created_at: string
  org_name: string
  branch_name: string
  seller_name: string
  quantity: number
  unit_price: string
  total_line: string
}

export interface ProductDetailResponse {
  product_id: string
  product_name: string
  items: ProductDetailRow[]
  total: number
  offset: number
  limit: number
}

export interface BranchDetailTopProduct {
  sku: string
  name: string
  units: number
  revenue: string
}

export interface BranchDetailTopSeller {
  full_name: string
  transactions: number
  revenue: string
}

export interface BranchDetailResponse {
  branch_id: number
  branch_name: string
  top_products: BranchDetailTopProduct[]
  top_sellers: BranchDetailTopSeller[]
}

export interface SellerDetailRow {
  document_id: string
  folio: number
  created_at: string
  total_amount: string
  branch_name: string
  customer_name: string | null
}

export interface SellerDetailResponse {
  user_id: number
  full_name: string
  items: SellerDetailRow[]
  total: number
  offset: number
  limit: number
}

export interface CustomerDetailRow {
  document_id: string
  folio: number
  created_at: string
  branch_name: string
  total_amount: string
  payment_method: string | null
  status: string
}

export interface CustomerDetailResponse {
  customer_id: number
  customer_name: string
  items: CustomerDetailRow[]
  total: number
  offset: number
  limit: number
}
