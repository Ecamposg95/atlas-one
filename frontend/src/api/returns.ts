import client from './client'

export type ReturnStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export interface ReturnItemVariant {
  id: string
  sku: string | null
  product_name: string | null
}

export interface ReturnLineItem {
  id: string
  return_id: string
  variant_id: string
  quantity: number
  refund_amount: number
  is_inventory_reentry: boolean
  variant: ReturnItemVariant | null
}

export interface ReturnUser {
  id: number
  username: string
  full_name: string | null
}

export interface ReturnBranch {
  id: number
  name: string
}

export interface ReturnDocument {
  id: string
  sale_id: string
  reason: string
  total_refunded: number
  refund_method: string
  status: ReturnStatus
  branch_id: number | null
  branch: ReturnBranch | null
  user: ReturnUser | null
  supervisor: ReturnUser | null
  created_at: string
  items: ReturnLineItem[]
}

/** Display helpers */
export function returnLabel(r: Pick<ReturnDocument, 'id' | 'sale_id'>): string {
  return `DEV-${r.id.slice(-6).toUpperCase()}`
}
export function returnRequestedBy(r: Pick<ReturnDocument, 'user'>): string {
  return r.user?.full_name ?? r.user?.username ?? '—'
}
export function returnApprovedBy(r: Pick<ReturnDocument, 'supervisor'>): string {
  return r.supervisor?.full_name ?? r.supervisor?.username ?? '—'
}
export function returnBranchName(r: Pick<ReturnDocument, 'branch'>): string | null {
  return r.branch?.name ?? null
}

export interface CreateReturnPayload {
  sale_id: string
  reason: string
  total_refunded: number
  refund_method?: string   // CASH | CARD | TRANSFER | OTHER — default CASH en el backend
  cash_session_id?: number | null
  items: {
    variant_id: string
    quantity: number
    refund_amount: number
    is_inventory_reentry: boolean
  }[]
}

export const returnsApi = {
  list: async (params?: { status?: ReturnStatus; branch_id?: number; start_date?: string; end_date?: string }): Promise<ReturnDocument[]> => {
    const { data } = await client.get<ReturnDocument[]>('/returns/', { params })
    return Array.isArray(data) ? data : (data as any)?.items ?? []
  },

  getById: async (id: string): Promise<ReturnDocument> => {
    const { data } = await client.get<ReturnDocument>(`/returns/${id}`)
    return data
  },

  create: async (payload: CreateReturnPayload): Promise<ReturnDocument> => {
    const { data } = await client.post<ReturnDocument>('/returns/', payload)
    return data
  },

  /**
   * Aprobar devolución. `force=true` se requiere para reembolsos en
   * EFECTIVO mayores a $10,000 (R-3 fat-finger guard). El backend
   * devuelve 400 con mensaje del umbral si force es false; el caller
   * debe confirmar con el usuario y reintentar con force=true.
   */
  approve: async (id: string, force = false): Promise<ReturnDocument> => {
    const { data } = await client.post<ReturnDocument>(
      `/returns/${id}/approve`,
      null,
      force ? { params: { force: true } } : undefined,
    )
    return data
  },

  reject: async (id: string, reason?: string): Promise<ReturnDocument> => {
    const { data } = await client.post<ReturnDocument>(`/returns/${id}/reject`, { reason })
    return data
  },

  getBySale: async (saleId: string): Promise<ReturnDocument[]> => {
    const { data } = await client.get<ReturnDocument[]>(`/returns/sale/${saleId}`)
    return Array.isArray(data) ? data : (data as any)?.items ?? []
  },
}
