/**
 * Matriz color × talla del alta de producto (preset boutique).
 *
 * Funciones puras: el formulario solo pinta lo que sale de aquí. Cada fila es
 * una variante candidata; la principal (la del SKU base) no está en la matriz.
 */
export interface VariantRow {
  key: string // "rojo|m" — identidad estable entre regeneraciones
  color: string
  size: string
  sku: string
  barcode: string
  price: string // vacío = hereda el precio base
  initial_stock: string // vacío o 0 = nace sin existencia
  /** El admin escribió el SKU a mano: cambiar el SKU base ya no lo pisa. */
  skuTocado?: boolean
}

export interface ExtraVariantPayload {
  color?: string
  size?: string
  sku?: string
  barcode?: string
  price?: number
  initial_stock?: number
}

/** Pareja color/talla que el producto YA tiene (edición): no se regenera. */
export interface VariantPair {
  color?: string | null
  size?: string | null
}

export function parseList(text: string): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of text.split(/[,\n]/)) {
    const v = raw.trim()
    if (!v) continue
    const k = v.toLowerCase()
    if (seen.has(k)) continue
    seen.add(k)
    out.push(v)
  }
  return out
}

/** "Azul marino" → "AZULMARINO": mayúsculas, sin acentos ni espacios. */
export function skuPart(text: string): string {
  return text.normalize('NFKD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/[^A-Z0-9]/g, '')
}

const rowKey = (color: string, size: string) => `${color.toLowerCase()}|${size.toLowerCase()}`

const skuSugerido = (baseSku: string, color: string, size: string) =>
  [baseSku.trim(), ...[color, size].filter(Boolean).map(skuPart)].filter(Boolean).join('-')

/**
 * Filas de la matriz para los colores × tallas escritos.
 *
 * `previous` conserva lo que el admin ya tecleó en filas que siguen vivas. El
 * SKU sugerido se recalcula al cambiar el SKU base —antes las filas se
 * quedaban con el prefijo viejo—, salvo en las filas con `skuTocado`.
 * `existing` son las parejas que el producto ya tiene (edición): se omiten
 * para no chocar con el 409 "Ya existe la variante".
 */
export function buildVariantRows(
  baseSku: string,
  colors: string[],
  sizes: string[],
  previous: VariantRow[],
  existing: VariantPair[] = [],
): VariantRow[] {
  const cs = colors.length ? colors : ['']
  const ss = sizes.length ? sizes : ['']
  const prev = new Map(previous.map((r) => [r.key, r]))
  const yaExiste = new Set(existing.map((e) => rowKey(e.color ?? '', e.size ?? '')))
  const rows: VariantRow[] = []
  for (const color of cs) {
    for (const size of ss) {
      if (!color && !size) continue
      const key = rowKey(color, size)
      if (yaExiste.has(key)) continue
      const sku = skuSugerido(baseSku, color, size)
      const old = prev.get(key)
      if (old) {
        rows.push({ ...old, color, size, sku: old.skuTocado ? old.sku : sku })
        continue
      }
      rows.push({ key, color, size, sku, barcode: '', price: '', initial_stock: '' })
    }
  }
  return rows
}

export function toExtraVariants(rows: VariantRow[]): ExtraVariantPayload[] {
  return rows.map((r) => {
    const out: ExtraVariantPayload = {}
    if (r.color) out.color = r.color
    if (r.size) out.size = r.size
    if (r.sku.trim()) out.sku = r.sku.trim()
    if (r.barcode.trim()) out.barcode = r.barcode.trim()
    const p = Number(r.price)
    if (r.price.trim() && Number.isFinite(p) && p > 0) out.price = p
    const s = Number(r.initial_stock)
    if (r.initial_stock.trim() && Number.isFinite(s) && s > 0) out.initial_stock = s
    return out
  })
}

/**
 * Parte la matriz en variante principal + hermanas.
 *
 * La PRIMERA fila es la principal: sus color/talla viajan en el payload del
 * producto (`color`/`size`) y su SKU es el SKU base, así que no se manda en
 * `extra_variants`. Antes se mandaban todas y el backend creaba además una
 * "Estándar" sin talla: una prenda con S/M/L nacía con cuatro variantes y el
 * POS pintaba una celda "—" invendible.
 */
export function splitPrincipal(rows: VariantRow[]): { principal: VariantRow | null; extras: VariantRow[] } {
  if (rows.length === 0) return { principal: null, extras: [] }
  return { principal: rows[0], extras: rows.slice(1) }
}

/**
 * Traduce las marcas de campo que devuelve el backend a las claves que pinta
 * la matriz: un 422 llega como `extra_variants.0.sku` y la tabla busca
 * `variants.0.sku`. Sin esto el error se quedaba en el aviso de arriba y la
 * fila culpable no se marcaba.
 */
export function variantFieldErrors(errores: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [campo, msg] of Object.entries(errores)) {
    out[campo.startsWith('extra_variants.') ? campo.replace('extra_variants.', 'variants.') : campo] = msg
  }
  return out
}

/** Campo de la fila al que apunta un mensaje del backend, si lo dice. */
function campoDelMensaje(msg: string): string {
  if (/sku/i.test(msg)) return 'sku'
  if (/c[oó]digo de barras/i.test(msg)) return 'barcode'
  if (/precio/i.test(msg)) return 'price'
  if (/existencia/i.test(msg)) return 'initial_stock'
  return ''
}

/**
 * Marca la fila culpable a partir del `detail` de texto del backend.
 *
 * `crear_variantes` responde dos formas: con índice —"variants[1]: el precio
 * debe ser mayor a cero"— y sin él, citando el dato repetido —"El SKU 'PLY-L'
 * ya existe…"—. Antes las dos acababan en un toast y el admin tenía que
 * adivinar qué talla corregir; aquí se traducen a la clave que pinta la matriz.
 * `extras` son las filas hermanas (la principal no viaja en `extra_variants`).
 */
export function variantDetailErrors(detail: unknown, extras: VariantRow[]): Record<string, string> {
  if (typeof detail !== 'string') return {}
  const texto = detail.trim()
  if (!texto) return {}

  const conIndice = texto.match(/^variants\[(\d+)\]:\s*(.+)$/i)
  if (conIndice) {
    const n = Number(conIndice[1])
    const msg = conIndice[2].trim()
    const campo = campoDelMensaje(msg)
    return { [campo ? `variants.${n}.${campo}` : `variants.${n}`]: msg }
  }

  const sku = texto.match(/SKU '([^']+)'/i)
  if (sku) {
    const i = extras.findIndex((r) => r.sku.trim().toLowerCase() === sku[1].trim().toLowerCase())
    if (i >= 0) return { [`variants.${i}.sku`]: texto }
  }
  const barcode = texto.match(/c[oó]digo de barras '([^']+)'/i)
  if (barcode) {
    const i = extras.findIndex((r) => r.barcode.trim() === barcode[1].trim())
    if (i >= 0) return { [`variants.${i}.barcode`]: texto }
  }
  return {}
}
