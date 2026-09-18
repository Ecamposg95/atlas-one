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

  pay: async (id: number, payload: { amount: number; method?: string; reference?: string }): Promise<LedgerEntry> => {
    const { data } = await client.post<LedgerEntry>(`/customers/${id}/pay`, payload)
    return data
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
