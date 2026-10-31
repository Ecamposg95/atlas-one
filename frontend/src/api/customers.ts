import client from './client'

export interface Customer {
  id: number
  name: string
  phone: string | null
  email: string | null
  tax_id: string | null
  address: string | null
  zip_code?: string | null
  notes?: string | null
  has_credit?: boolean
  credit_days?: number | null
  current_balance: number
  credit_limit: number | null
  portal_active?: boolean
}

export interface CustomerPayload {
  name: string
  phone?: string | null
  email?: string | null
  tax_id?: string | null
  address?: string | null
  zip_code?: string | null
  notes?: string | null
  has_credit?: boolean
  credit_limit?: number
  credit_days?: number
}

export interface CustomerStats {
  total: number
  total_debt: number
  total_credit: number
  with_debt: number
  with_credit: number
}

export interface LedgerEntry {
  id: number
  amount: number
  description: string | null
  sales_document_id: string | null
  created_at: string
}

export interface UnpaidDocument {
  id: string
  folio: string
  created_at: string
  total_amount: number
  paid_amount: number
  balance: number
  doc_type: string
}

export interface CobranzaItem {
  id: number
  name: string | null
  phone: string | null
  balance: number
  cargo_mas_viejo: string | null
  dias: number
  ultimo_abono: string | null
  branch_id: number | null
  branch_name: string | null
  tickets_abiertos: number
  antiguedad: Record<'current' | '31_60' | '61_90' | '91_plus', number>
}

export interface CobranzaResumen { por_cobrar: number; vencido_30: number; clientes: number; a_favor: number }

export interface CobranzaResponse { resumen: CobranzaResumen; items: CobranzaItem[]; total: number }

export interface AbonoAplicado {
  sales_document_id: string
  folio: string
  amount: number
  paid_in_full: boolean
}

/** Respuesta de POST /customers/{id}/pay (spec 2026-10-29 §4.2). */
export interface AbonoResponse {
  entries: LedgerEntry[]
  customer_balance_before: number
  customer_balance_after: number
  applied: AbonoAplicado[]
  unapplied: number
  payment_id: string
  method: string
  reference: string | null
  received_at: string
}

export interface CustomerListResponse {
  items: Customer[]
  total: number
}

export const customersApi = {
  search: async (q: string, limit = 10): Promise<Customer[]> => {
    // El backend filtra con `search`, no `q`: con `q` FastAPI lo ignoraba y
    // devolvía los primeros `limit` clientes en orden alfabético, así que el
    // POS "encontraba" siempre al mismo cliente equivocado.
    const { data } = await client.get<Customer[]>('/customers/', { params: { search: q, limit } })
    return Array.isArray(data) ? data : (data as any)?.items ?? []
  },

  getAll: async (params?: { skip?: number; limit?: number; search?: string; balance_filter?: string; paginate?: boolean }): Promise<CustomerListResponse> => {
    const { data } = await client.get<CustomerListResponse>('/customers/', {
      params: { paginate: true, limit: 50, ...params },
    })
    if (Array.isArray(data)) return { items: data, total: data.length }
    return { items: data?.items ?? [], total: data?.total ?? 0 }
  },

  getById: async (id: number): Promise<Customer> => {
    const { data } = await client.get<Customer>(`/customers/${id}`)
    return data
  },

  getStats: async (): Promise<CustomerStats> => {
    const { data } = await client.get<CustomerStats>('/customers/stats')
    return data
  },

  getStatement: async (id: number, params?: { limit?: number; start_date?: string; end_date?: string }): Promise<LedgerEntry[]> => {
    const { data } = await client.get<LedgerEntry[]>(`/customers/${id}/statement`, { params })
    return Array.isArray(data) ? data : (data as any)?.items ?? []
  },

  pay: async (id: number, payload: { amount: number; method?: string; reference?: string; sales_document_id?: string }): Promise<AbonoResponse> => {
    const { data } = await client.post<AbonoResponse>(`/customers/${id}/pay`, payload)
    return data
  },

  getUnpaidDocuments: async (id: number): Promise<UnpaidDocument[]> => {
    const { data } = await client.get<UnpaidDocument[]>(`/customers/${id}/unpaid-documents`)
    return Array.isArray(data) ? data : []
  },

  /** GET /customers/cobranza (spec 2026-10-29 §3.1): solo roles de oficina. */
  cobranza: async (params?: { branch_id?: number; bucket?: string; search?: string; order?: 'saldo' | 'antiguedad'; skip?: number; limit?: number }): Promise<CobranzaResponse> => {
    const { data } = await client.get<CobranzaResponse>('/customers/cobranza', { params })
    // Los Decimal del backend llegan como cadenas; se convierten aquí para que la pantalla no lo haga.
    const num = (v: unknown) => Number(v ?? 0)
    return {
      total: data.total,
      resumen: { por_cobrar: num(data.resumen.por_cobrar), vencido_30: num(data.resumen.vencido_30), clientes: data.resumen.clientes, a_favor: num(data.resumen.a_favor) },
      items: data.items.map((i) => ({
        ...i, balance: num(i.balance),
        antiguedad: { current: num(i.antiguedad.current), '31_60': num(i.antiguedad['31_60']), '61_90': num(i.antiguedad['61_90']), '91_plus': num(i.antiguedad['91_plus']) },
      })),
    }
  },

  create: async (payload: CustomerPayload): Promise<Customer> => {
    const { data } = await client.post<Customer>('/customers/', payload)
    return data
  },

  update: async (id: number, payload: Partial<CustomerPayload>): Promise<Customer> => {
    const { data } = await client.put<Customer>(`/customers/${id}`, payload)
    return data
  },

  delete: async (id: number): Promise<Customer> => {
    const { data } = await client.delete<Customer>(`/customers/${id}`)
    return data
  },

  getStatementPdf: async (id: number, params?: { start_date?: string; end_date?: string }): Promise<Blob> => {
    const { data } = await client.get(`/customers/${id}/pdf-statement`, {
      params,
      responseType: 'blob',
    })
    return data
  },
}
