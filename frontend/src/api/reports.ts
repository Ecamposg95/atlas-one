import client from './client'

export interface DashboardData {
  kpis: {
    /** Venta NETA del periodo (cobradas − devoluciones aprobadas). */
    sales: number
    gross_sales?: number
    returns?: number
    returns_count?: number
    orders: number
    avg_ticket: number
    pending: number
    draft: number
    total_products: number
    transit_shipments: number
    unique_skus_sold?: number
    // Comparativo del periodo anterior (mismo largo).
    prev_sales?: number
    prev_orders?: number
    prev_avg_ticket?: number
    prev_returns?: number
    /** Utilidad bruta solo sobre renglones con costo; null para roles sin costos (gerente). */
    gross_profit?: number | null
    prev_gross_profit?: number | null
    /** Lo vendido en renglones sin costo (fuera de la utilidad). */
    sales_without_cost?: number | null
    sales_with_cost?: number | null
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
  // `total` = importe (Fase 2); `trend` (opcional): piezas por día alineadas al rango.
  top_products: { name: string; qty: number; total?: number; trend?: number[] }[]
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
  /** Departamento al que se acotó la consulta (UUID); null = todos. */
  department_id?: string | null
  ve_costo: boolean
  totales: ValuacionTotales
  grupos: ValuacionGrupo[]
}

// --- Inicio del dueño (GET /reports/inicio; modo básico 2026-10 + SP6) ----
export interface PeriodoVentas {
  desde: string
  hasta: string
  /** Venta NETA: cobradas menos devoluciones aprobadas del periodo. */
  total: number
  devuelto: number
  tickets: number
}

export interface ProductoTop {
  nombre: string
  cantidad: number
  total: number
}

export interface ProductoPocaExistencia {
  variant_id: string
  nombre: string
  sku: string
  existencia: number
}

export interface CorteInicio {
  estado: 'abierto' | 'cerrado' | 'sin_turno'
  cajera: string | null
  abierto_en: string | null
  cerrado_en: string | null
  /** Solo con turno abierto. */
  efectivo_esperado: number | null
  /** Solo con turno cerrado. */
  efectivo_contado: number | null
}

export interface ProductoSinMovimiento {
  variant_id: string
  nombre: string
  sku: string
  existencia: number
  /** existencia × precio base. */
  importe_venta: number
}

export interface DiferenciaCaja {
  session_id: number
  sucursal: string
  cajera: string | null
  cerrado_en: string | null
  esperado: number
  contado: number
  /** contado − esperado. */
  diferencia: number
}

export interface SucursalInicio {
  branch_id: number
  nombre: string
  /** Neta. */
  ventas_hoy: number
  devuelto_hoy: number
  tickets_hoy: number
  corte: CorteInicio
  poca_existencia: number
}

export interface DiaTendencia {
  fecha: string
  neta: number
  tickets: number
}

/** Hoy y los 6 anteriores (`dias`) y los 7 previos (`anterior`), netos, día de México. */
export interface Tendencia {
  dias: DiaTendencia[]
  anterior: DiaTendencia[]
}

export interface HoraInicio {
  hora: number
  neta: number
  tickets: number
}

/** GET /reports/inicio (SP6). Las secciones nuevas solo llegan con `completo: true`; en básico son null. */
export interface Inicio {
  /** null = todas las sucursales de la org. */
  branch_id: number | null
  hoy: PeriodoVentas
  ayer: PeriodoVentas
  semana: PeriodoVentas
  por_metodo_hoy: Record<string, number>
  top_semana: ProductoTop[]
  poca_existencia: { umbral: number; productos: ProductoPocaExistencia[] }
  corte: CorteInicio
  sin_movimiento: { dias: number; productos: ProductoSinMovimiento[] } | null
  pendientes: { devoluciones: number; turnos_abiertos: number; diferencias_caja: DiferenciaCaja[] } | null
  /** null = una sola sucursal que vende, o se pidió una sucursal. */
  sucursales: SucursalInicio[] | null
  /** null = sin `completo` o rol que no ve costos. Solo renglones con costo. */
  utilidad_bruta_hoy: number | null
  /** Lo vendido hoy en renglones sin costo (fuera de la utilidad). */
  venta_sin_costo_hoy: number | null
  /** Fase 2: solo con `completo: true` (el Inicio básico no pinta gráficas); null en básico. */
  tendencia: Tendencia | null
  /** 24 horas de hoy; el frontend recorta la ventana con `recortarHoras`. */
  por_hora_hoy: HoraInicio[] | null
  /** Para la variación de la utilidad de hoy; null sin `completo` o sin costos. */
  utilidad_bruta_ayer: number | null
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
    params: { agrupar?: AgruparValuacion; branch_id?: number; department_id?: string } = {},
  ): Promise<ValuacionInventario> => {
    const { data } = await client.get<ValuacionInventario>('/reports/valor-inventario', { params })
    return data
  },

  inicio: async (params: { branch_id?: number; completo?: boolean; dias_sin_movimiento?: number } = {}): Promise<Inicio> => {
    const { data } = await client.get<Inicio>('/reports/inicio', { params })
    return data
  },
}
