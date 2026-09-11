import client from './client'
import type { SalesDocument, CartItem } from '../types/sales'

export interface SalesListResponse {
  items: SalesDocument[]
  total: number
  page: number
  pages: number
}

export interface SaleCreateResponse {
  status: string
  sale_id: string
  folio: string
  total: number
  paid: number
  change: number
  credit_debt: number
}

interface CreateSalePayload {
  customer_id?: number | null
  items: CartItem[]
  payments: { method: string; amount: number; reference?: string }[]
  notes?: string
  doc_type?: string
  requires_invoice?: boolean
  global_discount_pct?: number          // % aplicado al ticket; backend lo persiste para auditoría
  parked_ticket_id?: string             // si la venta resuelve un ticket pausado, marcar CONVERTED
}

export interface SalesStats {
  total_sales: number
  total_transactions: number
  average_ticket: number
  payment_methods: Record<string, number>
  refund_count: number
  refund_total: number
  peak_hour: string | null
}

// Track 2 (POS bug-fix): tickets pausados — tabla aparte, hand-off entre PCs.
export interface ParkedTicket {
  id: string
  branch_id: number
  user_id: number
  customer_id: number | null
  cart_json: Record<string, unknown>
  notes: string | null
  parked_at: string
  expires_at: string | null
}

export const salesApi = {
  getStats: async (params: { start_date: string; end_date: string; branch_id?: number }): Promise<SalesStats> => {
    const { data } = await client.get<SalesStats>('/sales/stats', { params })
    return data ?? { total_sales: 0, total_transactions: 0, average_ticket: 0, payment_methods: {}, refund_count: 0, refund_total: 0, peak_hour: null }
  },

  /**
   * `params` acepta, entre otros, `folio_search` (folio exacto — tolera
   * serie/ceros a la izquierda, ver `app/routers/sales.py::read_sales`), usado
   * por `ReturnModal` para localizar el ticket a devolver.
   */
  list: async (params?: Record<string, unknown>): Promise<SalesListResponse> => {
    const { data } = await client.get<SalesListResponse>('/sales/', { params })
    if (Array.isArray(data)) return { items: data, total: data.length, page: 0, pages: 1 }
    return { items: data?.items ?? [], total: data?.total ?? 0, page: data?.page ?? 0, pages: data?.pages ?? 1 }
  },

  getById: async (id: string): Promise<SalesDocument> => {
    const { data } = await client.get<SalesDocument>(`/sales/${id}`)
    return data
  },

  getMyLast: async (): Promise<SalesDocument | null> => {
    try {
      const { data } = await client.get<SalesDocument>('/sales/my-last')
      return data
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status
      if (status === 404) return null
      throw e
    }
  },

  create: async (payload: CreateSalePayload): Promise<SaleCreateResponse> => {
    const { data } = await client.post<SaleCreateResponse>('/sales/', payload)
    return data
  },

  delete: async (id: string): Promise<void> => {
    await client.delete(`/sales/${id}`)
  },
}

export const parkedTicketsApi = {
  list: async (): Promise<ParkedTicket[]> => {
    const { data } = await client.get<ParkedTicket[]>('/sales/parked')
    return Array.isArray(data) ? data : []
  },

  get: async (id: string): Promise<ParkedTicket> => {
    const { data } = await client.get<ParkedTicket>(`/sales/parked/${id}`)
    return data
  },

  park: async (cartJson: Record<string, unknown>, customer_id?: number | null, notes?: string): Promise<ParkedTicket> => {
    const { data } = await client.post<ParkedTicket>('/sales/parked', {
      cart_json: cartJson,
      customer_id: customer_id ?? null,
      notes: notes ?? null,
    })
    return data
  },

  resume: async (id: string): Promise<ParkedTicket> => {
    const { data } = await client.post<ParkedTicket>(`/sales/parked/${id}/resume`)
    return data
  },

  update: async (
    id: string,
    cartJson: Record<string, unknown>,
    notes?: string,
  ): Promise<ParkedTicket> => {
    const { data } = await client.patch<ParkedTicket>(`/sales/parked/${id}`, {
      cart_json: cartJson,
      notes: notes ?? null,
    })
    return data
  },

  remove: async (id: string): Promise<void> => {
    await client.delete(`/sales/parked/${id}`)
  },
}
