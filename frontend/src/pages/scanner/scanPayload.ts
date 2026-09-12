import type { Product, ProductPrice } from '../../types/products'

/** Mapa `id de escalón -> precio nuevo` con lo que el admin tocó en pantalla. */
export type TierEdits = Record<string, number>

export interface PriceUpdatePayload {
  price: number
  prices?: Array<{
    price_name: string
    min_quantity: number
    unit_price: number
    linked_package_id: string | null
  }>
}

/**
 * Arma el body del `PUT /api/products/{id}` para un cambio de precios.
 *
 * `prices` es REEMPLAZO COMPLETO en el backend: borra todos los ProductPrice de
 * la variante y recrea los que reciba (core.py, "Update Prices (Complete
 * Replacement)"). Por eso aquí siempre se reconstruye la lista ENTERA a partir
 * del producto, aplicando encima solo los escalones editados. Mandar únicamente
 * el que se tocó borraría los demás del catálogo.
 *
 * Se conservan `min_quantity` y `linked_package_id` tal como venían: el segundo
 * es lo que hace que un escalón sea la caja, y perderlo cambia la etiqueta que
 * se imprime en el ticket.
 */
/** Campos de ficha que el scanner puede tocar. Ausente = no se toca. */
export interface DetailEdits {
  name?: string
  department_id?: string | null
  brand_id?: string | null
  barcode?: string | null
}

export interface DetailsUpdatePayload {
  name?: string
  department_id?: string | null
  brand_id?: string | null
  barcode?: string | null
}

/**
 * Arma el body del `PUT /api/products/{id}` para un cambio de FICHA.
 *
 * Deliberadamente NO incluye `prices` ni `packaging_units`: ambos son
 * reemplazo completo en el backend, así que mandarlos —aunque fuera por
 * copiar el producto entero— borraría los escalones y los empaques del
 * catálogo. Solo viajan los campos presentes en `edits`.
 *
 * Diferencia intencional entre nombre y código: un nombre vacío se ignora
 * (el producto quedaría sin identidad), mientras que un código vacío viaja
 * como `null` porque borrarlo es una acción legítima.
 */
export function buildDetailsUpdatePayload(
  _product: Product,
  edits: DetailEdits,
): DetailsUpdatePayload {
  const payload: DetailsUpdatePayload = {}

  if (edits.name !== undefined) {
    const name = edits.name.trim()
    if (name) payload.name = name
  }
  if (edits.barcode !== undefined) {
    const code = (edits.barcode ?? '').trim()
    payload.barcode = code || null
  }
  if (edits.department_id !== undefined) payload.department_id = edits.department_id
  if (edits.brand_id !== undefined) payload.brand_id = edits.brand_id

  return payload
}

export function buildPriceUpdatePayload(
  product: Product,
  basePrice: number,
  edits: TierEdits,
): PriceUpdatePayload {
  const tiers: ProductPrice[] = product.prices ?? []
  const payload: PriceUpdatePayload = { price: basePrice }

  // Sin escalones no se manda el campo: `prices: []` los BORRARÍA.
  if (tiers.length === 0) return payload

  payload.prices = tiers.map((t) => ({
    price_name: t.price_name,
    min_quantity: t.min_quantity,
    unit_price: edits[t.id] ?? t.unit_price,
    linked_package_id: t.linked_package_id ?? null,
  }))
  return payload
}
