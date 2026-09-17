import client from './client'

export interface Organization {
  id: number
  name: string
  tax_id: string | null
  address: string | null
  phone: string | null
  email: string | null
  logo_url: string | null
  ticket_header: string | null
  ticket_footer: string | null
  industry_type: string | null
  // Equivalente en dólares (2026-09-17). 'off' = la función está apagada y no
  // se muestra nada en el POS ni en el ticket.
  usd_rate_mode?: 'off' | 'auto' | 'manual'
  usd_rate_manual?: number | string | null
  usd_rate_margin?: number | string
  // Comisión por pago con tarjeta (2026-09-17). 0 = apagada: no se cobra ni se
  // muestra nada en el POS, el ticket, el corte ni los reportes.
  card_surcharge_pct?: number | string
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
