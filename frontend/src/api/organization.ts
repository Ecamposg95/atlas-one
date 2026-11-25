import client from './client'

/** Espejo de `app/modules/cargas/reglas.py`. Los Decimal viajan como texto. */
export interface TipoPrendaRegla { codigo_sku: string; departamento: string }
export interface RangoPrecioRegla { tipo: string; marca: string | null; precios: string[] }
export interface ReglasCarga {
  costo_si_falta: 'preguntar' | 'fraccion_precio'
  fraccion: string
  iva: boolean
  sucursal_recibe: number | null
  activar_en: 'todas_las_que_venden' | 'sucursal_recibe'
  mapa_tallas: Record<string, string>
  escala_ropa: string[]
  tipos: Record<string, TipoPrendaRegla>
  materiales_aparte: string[]
  material_normal: string | null
  genero_por_marca: Record<string, string>
  genero_por_omision: string | null
  sufijo_dama: string | null
  matriz_por_omision: 'completa' | 'solo_lo_que_hay'
  precios_familia: RangoPrecioRegla[]
  ventana_ya_cargado_dias: number
}

export const REGLAS_CARGA_POR_OMISION: ReglasCarga = {
  costo_si_falta: 'preguntar', fraccion: '0.5', iva: false, sucursal_recibe: null,
  activar_en: 'todas_las_que_venden', mapa_tallas: {}, escala_ropa: [], tipos: {},
  materiales_aparte: [], material_normal: null, genero_por_marca: {},
  genero_por_omision: null, sufijo_dama: null, matriz_por_omision: 'solo_lo_que_hay',
  precios_familia: [], ventana_ya_cargado_dias: 14,
}

export interface Organization {
  id: number
  name: string
  tax_id: string | null
  address: string | null
  phone: string | null
  email: string | null
  logo_url: string | null
  website: string | null
  ticket_header: string | null
  ticket_footer: string | null
  industry_type: string | null
  // Secciones boutique del ticket (2026-09-19). Vacías = la sección no se
  // imprime. `Web:` del ticket sale de `website`, no de un campo aparte.
  ticket_terms?: string | null
  ticket_terms_url?: string | null
  ticket_instagram?: string | null
  ticket_facebook?: string | null
  ticket_tiktok?: string | null
  ticket_whatsapp?: string | null
  ticket_show_vendor?: boolean
  // Renglón del producto en el ticket (2026-09-21). 'compact' = el de siempre
  // (una línea recortada); 'detailed' = marca / nombre completo / talla.
  ticket_line_style?: 'compact' | 'detailed'
  // Equivalente en dólares (2026-09-17). 'off' = la función está apagada y no
  // se muestra nada en el POS ni en el ticket.
  usd_rate_mode?: 'off' | 'auto' | 'manual'
  usd_rate_manual?: number | string | null
  usd_rate_margin?: number | string
  // Comisión por pago con tarjeta (2026-09-17). 0 = apagada: no se cobra ni se
  // muestra nada en el POS, el ticket, el corte ni los reportes.
  card_surcharge_pct?: number | string
  // Conteo ciego del corte de caja (2026-11-21). true = la caja no ve el
  // esperado ni su desglose con el turno abierto. Solo admin/dueño lo cambia.
  conteo_ciego?: boolean
  /** Días de ventas pasadas que la caja consulta y devuelve (0 = solo hoy). */
  dias_ventas_caja?: number | string
  /** Monto hasta el que la caja devuelve sin gerente (0 = siempre pide autorización). */
  devolucion_libre_hasta?: number | string
  // Precio por sucursal (2026-11-23). true = el precio que edita alguien con
  // sucursal solo cambia el de su sucursal. Solo admin/dueño lo cambia.
  precio_por_sucursal?: boolean
  // Modo básico (2026-10). `perfil_ui` lo cambia solo la plataforma; aquí se
  // lee y el PUT de tenant lo descarta. El tope es de "se está acabando".
  perfil_ui?: string | null
  umbral_poca_existencia?: number | null
  // Cargar mercancía con IA: solo ADMINISTRADOR/DUEÑO las escribe.
  ai_instrucciones?: string | null
  reglas_carga?: ReglasCarga | null
}

/** Respuesta de GET /api/organization/exchange-rate. */
export interface ExchangeRateInfo {
  mode: 'off' | 'auto' | 'manual'
  /** Tipo efectivo (ya con el margen). `null` = no mostrar nada. */
  rate: number | string | null
  source: 'banxico' | 'manual' | null
  fix_rate: number | string | null
  fix_date: string | null
  margin: number | string
  manual_rate: number | string | null
}

export interface Branch {
  id: number
  name: string
  branch_type: 'HQ' | 'STORE' | 'WAREHOUSE' | 'OFFICE'
  address: string | null
  phone: string | null
  is_headquarters: boolean
  is_active: boolean
  // El backend siempre lo manda (BranchRead); opcional aquí porque varias
  // pantallas construyen sucursales parciales para sus propios listados.
  can_sell?: boolean
}

export interface BranchCreate {
  name: string
  branch_type: Branch['branch_type']
  address?: string
  phone?: string
}

export const organizationApi = {
  getOrg: async (): Promise<Organization> => {
    const { data } = await client.get<Organization>('/organization/')
    return data
  },

  updateOrg: async (payload: Partial<Organization>): Promise<Organization> => {
    const { data } = await client.put<Organization>('/organization/', payload)
    return data
  },

  getExchangeRate: async (): Promise<ExchangeRateInfo> => {
    const { data } = await client.get<ExchangeRateInfo>('/organization/exchange-rate')
    return data
  },

  refreshExchangeRate: async (): Promise<{ ok: boolean; rate_date: string | null; rate: number | null }> => {
    const { data } = await client.post('/organization/exchange-rate/refresh')
    return data
  },

  getCardSurcharge: async (): Promise<{ pct: number | string }> => {
    const { data } = await client.get<{ pct: number | string }>('/organization/card-surcharge')
    return data
  },

  getBranches: async (): Promise<Branch[]> => {
    const { data } = await client.get<Branch[]>('/branches/')
    return Array.isArray(data) ? data : (data as any)?.items ?? []
  },

  createBranch: async (payload: BranchCreate): Promise<Branch> => {
    const { data } = await client.post<Branch>('/branches/', payload)
    return data
  },

  updateBranch: async (id: number, payload: Partial<BranchCreate>): Promise<Branch> => {
    const { data } = await client.put<Branch>(`/branches/${id}`, payload)
    return data
  },

  deleteBranch: async (id: number): Promise<void> => {
    await client.delete(`/branches/${id}`)
  },
}
