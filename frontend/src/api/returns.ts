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
  /** Motivo de catálogo; null en devoluciones anteriores al 2026-11-24. */
  reason_code?: string | null
  /** POLITICA (la caja sola) | PIN (gerente en la caja) | SUPERVISOR (aprobada después). */
  autorizacion?: string | null
  branch_id: number | null
  branch: ReturnBranch | null
  user: ReturnUser | null
  supervisor: ReturnUser | null
  /** Ticket de origen (serie y folio), para mostrarlo sin otra consulta. */
  sale?: { id: string; series?: string | null; folio?: number | null; customer_name?: string | null } | null
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

export interface MotivoDevolucion {
  code: string
  label: string
  regresa_a_stock: boolean
}

/** Respaldo del catálogo del servidor (`app/services/devoluciones.py::MOTIVOS`). */
export const MOTIVOS_DEVOLUCION: MotivoDevolucion[] = [
  { code: 'DEFECTO', label: 'Defecto', regresa_a_stock: false },
  { code: 'TALLA', label: 'Talla o medida', regresa_a_stock: true },
  { code: 'NO_GUSTO', label: 'No le gustó', regresa_a_stock: true },
  { code: 'ERROR_COBRO', label: 'Error de cobro', regresa_a_stock: true },
  { code: 'OTRO', label: 'Otro', regresa_a_stock: true },
]

export interface PiezaDevolvible {
  variant_id: string
  descripcion: string | null
  sku: string | null
  vendido: number | string
  devuelto: number | string
  en_tramite: number | string
  disponible: number | string
  /** Lo que el cliente pagó por pieza (ya con descuentos): es lo que se reembolsa. */
  precio_pagado: number | string
}

/** GET /returns/sale/{id}/piezas */
export interface PiezasDelTicket {
  piezas: PiezaDevolvible[]
  /** Métodos por los que se pagó el ticket: la caja reembolsa solo por esos. */
  metodos: string[]
  pendiente: { id: string; total: number | string } | null
  motivos: MotivoDevolucion[]
  /** Monto que la caja devuelve sin gerente; null si a este rol no le aplica tope. */
  monto_libre: number | string | null
  es_caja: boolean
}

export interface CreateReturnPayload {
  sale_id: string
  reason: string
  reason_code?: string
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
  list: async (params?: { status?: ReturnStatus; branch_id?: number; start_date?: string; end_date?: string; limit?: number }): Promise<ReturnDocument[]> => {
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

  /** Qué queda por devolver de un ticket, por dónde y con qué reglas. */
  piezas: async (saleId: string): Promise<PiezasDelTicket> => {
    const { data } = await client.get<PiezasDelTicket>(`/returns/sale/${saleId}/piezas`)
    return data
  },

  /** Un gerente autoriza la devolución pendiente tecleando su PIN en la caja. */
  autorizar: async (id: string, pin: string): Promise<ReturnDocument> => {
    const { data } = await client.post<ReturnDocument>(`/returns/${id}/autorizar`, { pin })
    return data
  },

  getBySale: async (saleId: string): Promise<ReturnDocument[]> => {
    const { data } = await client.get<ReturnDocument[]>(`/returns/sale/${saleId}`)
    return Array.isArray(data) ? data : (data as any)?.items ?? []
  },
}
