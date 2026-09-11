import type { Product } from '../../types/products'

/**
 * Lecturas seguras de la respuesta de producto.
 *
 * Ambas funciones existen por bugs que llegaron a producción el 2026-08-29 y
 * que ningún tipo de TypeScript atrapó — el tipo `Product` declara campos que
 * la API no manda, y `Number()` convierte basura en números plausibles.
 */

/** Decimal llega como cadena ("40.00") desde el backend; `Number` lo resuelve. */
function num(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

/**
 * Existencia del producto en la sucursal donde está parado el admin.
 *
 * `ProductRead` expone **`stock_total`**, no `stock` (app/schemas/products.py).
 * La ficha del scanner leía `product.stock` — `undefined` en runtime — así que
 * la base del conteo siempre era 0 y todo conteo se convertía en una ENTRADA:
 * contar 10 piezas de un producto con 40 registraba +10 y lo dejaba en 50. El
 * scanner no podía detectar un faltante de anaquel, solo inflar el inventario.
 *
 * Se prefiere `stock_levels` de la sucursal pedida porque el endpoint puede
 * devolver varias cuando el admin no tiene sucursal propia.
 */
export function currentStock(product: Product, branchId: number | null): number {
  if (branchId != null) {
    const nivel = (product.stock_levels ?? []).find((s) => s.branch_id === branchId)
    const q = num(nivel?.qty_on_hand)
    if (q !== null) return q
  }
  return num(product.stock_total) ?? 0
}

/**
 * Convierte lo tecleado en un escalón a un precio, o `null` si no lo es.
 *
 * `Number('')` es 0, y `edits[id] ?? unit_price` NO rescata el cero (`??` solo
 * atrapa null/undefined), así que vaciar el campo para reescribirlo guardaba el
 * escalón en $0.00 y el POS vendía a ese precio. Un precio de cero o negativo
 * no es un precio: es un campo a medio escribir.
 */
export function parseTierPrice(raw: string): number | null {
  const t = (raw ?? '').trim()
  if (!t) return null
  const n = Number(t)
  if (!Number.isFinite(n) || n <= 0) return null
  return n
}
