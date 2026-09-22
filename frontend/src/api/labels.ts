import client from './client'

/**
 * `/api/labels/*` — etiquetas de mostrador para la Zebra.
 *
 * El backend elige las variantes, calcula las copias y compone el ZPL; **no
 * imprime**. Devuelve el trabajo en base64 y el navegador se lo pasa al agente
 * local (`printerApi.printViaAgent`), el mismo transporte del ticket de venta.
 *
 * Contrato: `app/modules/labels/router.py`. Ninguna ruta lleva barra final —
 * el backend registra `/candidates`, `/preview`, `/jobs` y `/test` sin ella y
 * con `/` la petición cae en el catch-all de la SPA (el mismo tropiezo que ya
 * costó un bug en `/brands/{id}`).
 *
 * Todo el módulo está gateado por `require_module("labels")`: una cajera de una
 * org sin el módulo recibe 403 en los cuatro endpoints.
 */

/** Una variante viva con lo que la etiqueta y la tabla necesitan. */
export interface LabelCandidate {
  variant_id: string
  product_id: string
  sku: string
  barcode: string
  product_name: string
  /** Nombre completo de venta ("Marca · Prenda Modelo · Color, Talla M"). */
  sale_name: string
  brand: string
  department: string
  gender: string
  size: string
  color: string
  price: number
  stock: number
  /** Copias sugeridas = existencia, truncada y topada en 99. */
  copies_default: number
  printable: boolean
  /** Por qué NO se puede imprimir. `null` cuando `printable` es true. */
  reason: string | null
}

export interface LabelCandidatesResponse {
  items: LabelCandidate[]
  total: number
}

export interface LabelCandidatesFilters {
  search?: string
  department_id?: string
  brand_id?: string
  /** HOMBRE | MUJER | UNISEX | NINO. Un valor inválido da 422. */
  gender?: string
  only_with_stock?: boolean
  product_id?: string
}

/** Texto del layout. `x,y` es la esquina superior izquierda, en dots. */
export interface LabelTextElement {
  type: 'text'
  x: number
  y: number
  /** Alto de la letra en dots (el `h` de `^A0N,h,h`). */
  height: number
  text: string
  /** Ancho de la caja `^FB`; solo viene con `align: "R"`. */
  width: number | null
  align: string
}

/** Código de barras del layout, ya resuelto a módulos. */
export interface LabelBarcodeElement {
  type: 'barcode'
  x: number
  y: number
  height: number
  /** Cadena de módulos: '1' barra, '0' espacio. */
  bits: string
  /** Dots de ancho que mide CADA módulo. */
  module_width: number
  kind: string
  data: string
  /** Línea legible que la Zebra imprime bajo las barras. */
  interpretation: string
}

export type LabelElement = LabelTextElement | LabelBarcodeElement

export interface LabelPreview {
  /** Lienzo en dots: 408 × 200 (51 × 25 mm a 203 dpi). */
  width: number
  height: number
  kind: string
  /** Aviso del código angosto (`module_width: 1`), o cadena vacía. */
  warning: string
  elements: LabelElement[]
  zpl: string
}

/** Un renglón del lote: qué variante y cuántas copias. `copies` va de 1 a 99. */
export interface LabelJobItem {
  variant_id: string
  copies: number
}

export interface LabelSkipped {
  variant_id: string
  sku: string
  reason: string
}

export interface LabelJob {
  /** ZPL del lote en base64. Se pasa TAL CUAL al agente, sin decodificar. */
  content_base64: string
  /** Etiquetas que realmente lleva el trabajo (sin contar las omitidas). */
  labels: number
  skipped: LabelSkipped[]
}

export const labelsApi = {
  /** GET /api/labels/candidates — variantes que este usuario puede etiquetar. */
  candidates: async (filters: LabelCandidatesFilters = {}): Promise<LabelCandidatesResponse> => {
    const params: Record<string, unknown> = {}
    if (filters.search?.trim()) params.search = filters.search.trim()
    if (filters.department_id) params.department_id = filters.department_id
    if (filters.brand_id) params.brand_id = filters.brand_id
    if (filters.gender) params.gender = filters.gender
    if (filters.only_with_stock) params.only_with_stock = true
    if (filters.product_id) params.product_id = filters.product_id
    const { data } = await client.get<LabelCandidatesResponse>('/labels/candidates', { params })
    return { items: data?.items ?? [], total: data?.total ?? 0 }
  },

  /**
   * POST /api/labels/preview — elementos del layout + ZPL de UNA etiqueta.
   *
   * 404 si la variante no es visible para el usuario; 422 con el motivo si no
   * se puede imprimir (sin código de barras, código no imprimible).
   */
  preview: async (variantId: string): Promise<LabelPreview> => {
    const { data } = await client.post<LabelPreview>('/labels/preview', { variant_id: variantId })
    return data
  },

  /**
   * POST /api/labels/jobs — compone el lote y lo devuelve en base64.
   *
   * Un renglón malo no tumba el trabajo: se va a `skipped` con su motivo. Si
   * TODO se omite, `content_base64` viene vacío y no hay que mandarlo al
   * agente. El tope de 500 etiquetas se evalúa antes de mirar el catálogo y
   * responde 422 con un mensaje accionable.
   */
  createJob: async (items: LabelJobItem[]): Promise<LabelJob> => {
    const { data } = await client.post<LabelJob>('/labels/jobs', { items })
    return { content_base64: data?.content_base64 ?? '', labels: data?.labels ?? 0, skipped: data?.skipped ?? [] }
  },

  /** GET /api/labels/test — etiqueta de calibración en base64 (una copia). */
  testLabel: async (): Promise<string> => {
    const { data } = await client.get<{ content_base64?: string }>('/labels/test')
    return data?.content_base64 ?? ''
  },
}
