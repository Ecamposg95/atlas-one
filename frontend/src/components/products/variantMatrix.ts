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
}

export interface ExtraVariantPayload {
  color?: string
  size?: string
  sku?: string
  barcode?: string
  price?: number
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

export function buildVariantRows(
  baseSku: string,
  colors: string[],
  sizes: string[],
  previous: VariantRow[],
): VariantRow[] {
  const cs = colors.length ? colors : ['']
  const ss = sizes.length ? sizes : ['']
  const prev = new Map(previous.map((r) => [r.key, r]))
  const rows: VariantRow[] = []
  for (const color of cs) {
    for (const size of ss) {
      if (!color && !size) continue
      const key = rowKey(color, size)
      const old = prev.get(key)
      if (old) {
        rows.push({ ...old, color, size })
        continue
      }
      const sku = [baseSku.trim(), ...[color, size].filter(Boolean).map(skuPart)].filter(Boolean).join('-')
      rows.push({ key, color, size, sku, barcode: '', price: '' })
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
    return out
  })
}
