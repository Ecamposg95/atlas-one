import client from './client'

/**
 * Conteo físico con escáner (`/api/inventory/counts`). Los Numeric del
 * backend llegan como cadena ("3.00"): convertir con `num()` de
 * pages/inventory/conteos/avance.ts, nunca con `Number()` a ciegas.
 */

export interface ProductoResumen {
  variant_id: string
  nombre: string
  marca: string | null
  talla: string | null
  color: string | null
  sku: string | null
  barcode: string | null
  foto: string | null
  departamento: string | null
}

export interface Linea {
  id: number
  variant_id: string | null
  codigo: string | null
  qty_contada: string
  qty_sistema: string | null
  producto: ProductoResumen | null
  updated_at: string | null
}

export interface Avance {
  esperadas_variantes: number
  esperadas_piezas: string
  contadas_variantes: number
  contadas_piezas: string
  desconocidos: number
}

export interface Conteo {
  id: number
  branch_id: number
  branch_name: string | null
  department_id: string | null
  department_name: string | null
  status: 'ABIERTO' | 'CERRADO'
  notes: string | null
  created_by: string | null
  created_at: string | null
  closed_at: string | null
  avance: Avance
}

export interface ConteoDetalle extends Conteo { lineas: Linea[] }

export interface ScanResult {
  resultado: 'contado' | 'ambiguo' | 'desconocido'
  linea: Linea | null
  producto: ProductoResumen | null
  qty_sistema: string | null
  fuera_de_alcance: boolean
  candidatos: ProductoResumen[]
}

export interface FilaReporte {
  variant_id: string
  sku: string | null
  nombre: string
  marca: string | null
  talla: string | null
  color: string | null
  departamento: string | null
  sistema: string
  contado: string
  diferencia: string
}

export interface Reporte {
  estado: 'ABIERTO' | 'CERRADO'
  generado_en: string
  alcance: { sucursal: string | null; departamento: string | null }
  totales: Record<string, string | number>
  faltantes: FilaReporte[]
  sobrantes: FilaReporte[]
  fuera_de_alcance: FilaReporte[]
  desconocidos: { codigo: string; contado: string }[]
}

export const conteosApi = {
  listar: async (params?: { status?: string; branch_id?: number }): Promise<Conteo[]> => {
    const { data } = await client.get<Conteo[]>('/inventory/counts/', { params })
    return data
  },
  crear: async (body: { branch_id: number | null; department_id: string | null; notes?: string }): Promise<Conteo> => {
    const { data } = await client.post<Conteo>('/inventory/counts/', body)
    return data
  },
  ver: async (id: number): Promise<ConteoDetalle> => {
    const { data } = await client.get<ConteoDetalle>(`/inventory/counts/${id}`)
    return data
  },
  escanear: async (id: number, code: string): Promise<ScanResult> => {
    const { data } = await client.post<ScanResult>(`/inventory/counts/${id}/scan`, { code })
    return data
  },
  agregarLinea: async (id: number, variantId: string, qty = 1): Promise<Linea> => {
    const { data } = await client.post<Linea>(`/inventory/counts/${id}/lines`, { variant_id: variantId, qty: String(qty) })
    return data
  },
  fijarLinea: async (id: number, lineId: number, qty: number): Promise<Linea | null> => {
    const { data } = await client.patch<Linea | null>(`/inventory/counts/${id}/lines/${lineId}`, { qty_contada: String(qty) })
    return data
  },
  borrarLinea: async (id: number, lineId: number): Promise<void> => {
    await client.delete(`/inventory/counts/${id}/lines/${lineId}`)
  },
  cerrar: async (id: number): Promise<ConteoDetalle> => {
    const { data } = await client.post<ConteoDetalle>(`/inventory/counts/${id}/close`)
    return data
  },
  reporte: async (id: number): Promise<Reporte> => {
    const { data } = await client.get<Reporte>(`/inventory/counts/${id}/report`)
    return data
  },
}
