import client from './client'

/** Vale de tienda: saldo a favor que se entrega al devolver y se cobra en caja. */
export interface Vale {
  id: string
  code: string
  status: 'ACTIVO' | 'AGOTADO' | 'CANCELADO'
  initial_amount: number | string
  balance: number | string
  customer_id?: number | null
  customer_name?: string | null
  return_id?: string | null
  created_at?: string
  movimientos?: { kind: string; amount: number | string; created_at: string; sales_document_id?: string | null }[]
}

/** Referencia con la que el vale viaja como pago en el cobro (`OTHER`). */
export const referenciaDeVale = (code: string) => `VALE:${code}`

export const valesApi = {
  consultar: async (codigo: string): Promise<Vale> => {
    const { data } = await client.get<Vale>(`/vales/${encodeURIComponent(codigo.trim())}`)
    return data
  },
  listar: async (params?: { estado?: string; customer_id?: number; limit?: number }): Promise<{ items: Vale[]; total: number }> => {
    const { data } = await client.get<{ items: Vale[]; total: number }>('/vales/', { params })
    return data
  },
  cancelar: async (id: string): Promise<Vale> => {
    const { data } = await client.post<Vale>(`/vales/${id}/cancelar`)
    return data
  },
}
