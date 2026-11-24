import client from './client'

/**
 * `/api/cargas` — Cargar mercancía con IA (PDF o planilla → plan → catálogo).
 *
 * Tipos espejo del contrato HTTP de las cargas. Los decimales viajan como
 * texto ("1500.00"): conviértelos con cuidado, no con `Number()` a ciegas.
 * Ninguna ruta lleva barra final (la petición caería en el catch-all de la SPA).
 */

export type EstadoCarga = 'leyendo' | 'plan' | 'aplicando' | 'aplicada' | 'error' | 'descartada'
export type PropositoCarga = 'entrada' | 'migracion'
export type ClaseRenglon = 'EXISTE' | 'SUMA' | 'NUEVO' | 'YA_CARGADO' | 'IGNORADO'

export interface CargaResumen {
  id: string
  folio: number
  estado: EstadoCarga
  proposito: PropositoCarga
  archivo_nombre: string
  archivo_tipo: 'pdf' | 'xlsx' | 'csv'
  sucursal_destino_id: number | null
  sucursal_nombre: string | null
  piezas: string
  usuario: string
  created_at: string
  aplicada_at: string | null
  error: string | null
}

export interface OpcionDuda { clave: string; etiqueta: string }

export interface Duda {
  numero: number
  tipo: string
  texto: string
  opciones: OpcionDuda[]
  recomendada: string | null
  acepta_texto: boolean
  estado: 'abierta' | 'resuelta'
  respuesta: string | null
}

export interface RenglonPlan {
  orden: number
  talla: string | null
  color: string | null
  cantidad: string
  precio: string | null
  costo: string | null
  clase: ClaseRenglon
  sku: string | null
  origen: string
  /** Lo que decía el archivo en ese renglón (se enseña para ver qué se juntó). */
  descripcion: string
}

export interface GrupoPlan {
  /** Llave técnica; no se muestra. */
  grupo: string
  /** Lo que se enseña ("Marca Uno · Camisa lino"). */
  titulo: string
  marca: string | null
  tipo: string | null
  departamento: string | null
  genero: string | null
  product_id: string | null
  renglones: RenglonPlan[]
}

export interface CambioGrupo {
  grupo: string
  titulo: string
  renglones: number[]
  cambios: Record<string, { antes: unknown; despues: unknown }>
}

export interface CambioResumen {
  grupos: CambioGrupo[]
  dudas_resueltas: number[]
  dudas_nuevas: number[]
}

export interface Cambio {
  id: string
  secuencia: number
  texto: string | null
  resumen: CambioResumen
  deshecho: boolean
  puede_deshacer: boolean
  usuario: string
  created_at: string
}

export interface ConteoCerrado { departamento: string; numero: number; cerrado_at: string }

export interface ContadoresCarga {
  EXISTE: number
  SUMA: number
  NUEVO: number
  YA_CARGADO: number
  IGNORADO: number
  piezas: string
}

export interface CargaDetalle {
  carga: CargaResumen & { monedas: Record<string, string | null>; totales: Record<string, unknown> | null }
  contadores: ContadoresCarga
  dudas: Duda[]
  grupos: GrupoPlan[]
  cambios: Cambio[]
  ultimos_conteos: ConteoCerrado[]
  /** Rol ADMINISTRADOR/DUEÑO, estado plan y sin dudas abiertas. */
  puede_autorizar: boolean
}

export interface RespuestaCambio { cambio: Cambio | null; rechazos: string[] }

export interface Etiqueta {
  marca: string
  producto: string
  sku: string
  talla: string | null
  barcode: string | null
  piezas: string
  precio: string
}

export interface ResumenAplicacion {
  productos_nuevos: number
  variantes_nuevas: number
  piezas: string
  valor_costo: string
  etiquetas: Etiqueta[]
}

export interface CargaAlta { id: string; folio: number; estado: EstadoCarga }

export const cargasApi = {
  subir: async (archivo: File, proposito: PropositoCarga, sucursalId?: number): Promise<CargaAlta> => {
    const form = new FormData()
    form.append('archivo', archivo)
    form.append('proposito', proposito)
    if (sucursalId != null) form.append('sucursal_id', String(sucursalId))
    const { data } = await client.post<CargaAlta>('/cargas', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  listar: async (): Promise<CargaResumen[]> => {
    const { data } = await client.get<CargaResumen[]>('/cargas')
    return data
  },

  obtener: async (id: string): Promise<CargaDetalle> => {
    const { data } = await client.get<CargaDetalle>(`/cargas/${id}`)
    return data
  },

  responder: async (id: string, texto: string): Promise<RespuestaCambio> => {
    const { data } = await client.post<RespuestaCambio>(`/cargas/${id}/respuestas`, { texto })
    return data
  },

  resolverDuda: async (id: string, numero: number, opcion: string, valor?: string): Promise<RespuestaCambio> => {
    const { data } = await client.post<RespuestaCambio>(`/cargas/${id}/dudas/${numero}`, valor === undefined ? { opcion } : { opcion, valor })
    return data
  },

  deshacer: async (id: string, cambioId: string): Promise<CargaDetalle> => {
    const { data } = await client.post<CargaDetalle>(`/cargas/${id}/cambios/${cambioId}/deshacer`)
    return data
  },

  reintentar: async (id: string): Promise<CargaAlta> => {
    const { data } = await client.post<CargaAlta>(`/cargas/${id}/reintentar`)
    return data
  },

  autorizar: async (id: string): Promise<ResumenAplicacion> => {
    const { data } = await client.post<ResumenAplicacion>(`/cargas/${id}/autorizar`)
    return data
  },

  descartar: async (id: string): Promise<CargaAlta> => {
    const { data } = await client.post<CargaAlta>(`/cargas/${id}/descartar`)
    return data
  },

  etiquetas: async (id: string): Promise<Etiqueta[]> => {
    const { data } = await client.get<Etiqueta[]>(`/cargas/${id}/etiquetas`)
    return data
  },
}
