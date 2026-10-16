import client from './client'

export interface DashboardData {
  kpis: {
    sales: number
    orders: number
    avg_ticket: number
    pending: number
    draft: number
    total_products: number
    transit_shipments: number
    unique_skus_sold?: number
    // Previous-period comparatives (added 2026-04 for ultra redesign).
    prev_sales?: number
    prev_orders?: number
    prev_avg_ticket?: number
  }
  charts: {
    trend: { labels: string[]; data: number[] }
    // Parallel series aligned to `trend.labels` but with previous-period values.
    trend_previous?: { labels: string[]; data: number[] }
    hourly: { labels: string[]; data: number[] }
    payments: Record<string, { total: number; count: number }>
    // day: 0=Sunday ... 6=Saturday (PostgreSQL extract(dow)).
    heatmap?: { day: number; hour: number; amount: number; tickets: number }[]
  }
  // `trend` (optional): daily unit-qty series aligned to the date range.
  top_products: { name: string; qty: number; trend?: number[] }[]
  low_stock: { name: string; sku: string; stock: number }[]
  recent_sales: { folio: string; total: number; time: string; customer: string }[]
}

export interface WaiterSales {
  user_id: number
  name: string
  tickets: number
  revenue: number
  tips: number
  avg_ticket: number
}
export interface WaiterSalesResponse {
  start_date: string
  end_date: string
  waiters: WaiterSales[]
}

export interface SalesByHourResponse {
  date: string
  current_hour: number
  current_hour_amount: number
  current_hour_tickets: number
  hourly: { hour: number; amount: number; tickets: number }[]
}

export interface CommandCenterStats {
  global: {
    total_sales: number
    total_tickets: number
    ticket_average: number
    items_per_ticket: number
    canceled_tickets: number
    overrides_total: number
    returns_total: number
    sales_growth: number
  }
  payment_methods: Record<string, number>
  hourly_distribution: { hour: number; amount: number }[]
  branches: {
    id: number
    name: string
    status: string
    total_sales: number
    pending_cuts: number
    pending_users: { session_id: number; user: string; opened: string | null }[]
    critical_stock: number
    is_hq: boolean
  }[]
  alerts: { type: string; msg: string; source: string; time: string }[]
  top_products: { name: string; qty: number; value: number; metric: string }[]
  branches_included?: number[]
}

export interface DailySummary {
  date: string
  transactions_count: number
  total_revenue: number
  gross_profit: number
  payments: Record<string, number>
  top_selling_items: { name: string; quantity: number }[]
}

export interface AuditDiscrepancy {
  session_id: number
  branch_name: string
  opened_by: string
  opening_amount: number
  expected_cash: number
  closing_amount: number
  difference: number
  closed_at: string
}

// --- Valor de la tienda (GET /reports/valor-inventario) ---------------------
export type AgruparValuacion = 'sucursal' | 'departamento' | 'marca'

export interface ValuacionTotales {
  piezas: number
  skus: number
  valor_venta: number
  /** null cuando el rol no ve costos (gerente). */
  valor_costo: number | null
  piezas_sin_costo: number
  skus_sin_costo: number
}

export interface ValuacionGrupo {
  /** id de sucursal/departamento/marca como texto; '' = sin asignar. */
  clave: string
  nombre: string
  piezas: number
  skus: number
  valor_venta: number
  valor_costo: number | null
  piezas_sin_costo: number
}

export interface ValuacionInventario {
  agrupar: AgruparValuacion
  /** Sucursal consultada; null = todas las que venden. El gerente siempre recibe la suya. */
  branch_id: number | null
  ve_costo: boolean
  totales: ValuacionTotales
  grupos: ValuacionGrupo[]
}

export const reportsApi = {
  dashboard: async (params: { start_date: string; end_date: string; branch_id?: number }): Promise<DashboardData> => {
    const { data } = await client.get<DashboardData>('/reports/dashboard', { params })
    return data
  },

  salesByHour: async (params: { date: string; branch_id?: number }): Promise<SalesByHourResponse> => {
    const { data } = await client.get<SalesByHourResponse>('/reports/sales-by-hour', { params })
    return data
  },

  byWaiter: async (params: { start_date: string; end_date: string; branch_id?: number }): Promise<WaiterSalesResponse> => {
    const { data } = await client.get<WaiterSalesResponse>('/reports/by-waiter', { params })
    return data
  },

  topProducts: async (params: { start_date: string; end_date: string; branch_id?: number; limit?: number }) => {
    const { data } = await client.get('/reports/top-products', { params })
    return data
  },

  commandCenterStats: async (params: { start_date: string; end_date: string }): Promise<CommandCenterStats> => {
    const { data } = await client.get<CommandCenterStats>('/reports/command-center/stats', { params })
    return data
  },

  dailySummary: async (targetDate?: string, branchId?: number): Promise<DailySummary> => {
    const params: Record<string, string | number> = {}
    if (targetDate) params.target_date = targetDate
    if (branchId !== undefined) params.branch_id = branchId
    const { data } = await client.get<DailySummary>('/reports/daily-summary', {
      params: Object.keys(params).length ? params : undefined,
    })
    return data
  },

  agingReport: async (): Promise<{ ranges: { label: string; total: number; count: number }[] }> => {
    const { data } = await client.get('/reports/aging-report')
    return data
  },

  auditDiscrepancies: async (limit = 20): Promise<AuditDiscrepancy[]> => {
    const { data } = await client.get<AuditDiscrepancy[]>('/reports/audit/discrepancies', { params: { limit } })
    return Array.isArray(data) ? data : (data as any)?.items ?? []
  },

  exportCsv: async (params: { start_date: string; end_date: string; branch_id?: number }): Promise<void> => {
    const response = await client.get('/reports/export/csv', {
      params: { ...params, branch_id: params.branch_id ?? 0 },
      responseType: 'blob',
    })
    const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `reports_${params.start_date}_${params.end_date}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  },

  valorInventario: async (
    params: { agrupar?: AgruparValuacion; branch_id?: number } = {},
  ): Promise<ValuacionInventario> => {
    const { data } = await client.get<ValuacionInventario>('/reports/valor-inventario', { params })
    return data
  },
}
