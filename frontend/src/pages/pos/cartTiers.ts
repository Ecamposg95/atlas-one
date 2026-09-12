import type { CartItem } from '../../types/sales'

/** Misma clave que CartPanel.ck(): cart_key o, si falta, product_id. */
export const cartKeyOf = (item: CartItem): string => item.cart_key ?? item.product_id

/** Escalón de caja: el primero cuyo nombre contiene "caja". */
export const cajaTierOf = (item: CartItem) =>
  item.prices?.find((p) => p.price_name.toLowerCase().includes('caja'))

/**
 * Precio automático por cantidad total (piezas + cajas × piezas por caja).
 * Devuelve null cuando no hay nada que cambiar: sin escalones, precio forzado
 * por la cajera (`forcedPriceTier`, regla del dueño: dar precio de caja sin la
 * cantidad es lo normal), caja aplicada en bloque, o precio ya correcto.
 */
export function autoTierTarget(unit: CartItem, cajasQty: number): number | null {
  if (!unit.prices?.length) return null
  if (unit.forcedPriceTier) return null
  if (unit.cajaForcedByBulk) return null

  const unitsPerBox = cajaTierOf(unit)?.min_quantity ?? 1
  const totalUnits = unit.quantity + cajasQty * unitsPerBox

  const sorted = [...unit.prices].sort((a, b) => b.min_quantity - a.min_quantity)
  const matched = sorted.find((t) => totalUnits >= t.min_quantity)
  const target = matched?.unit_price ?? (unit.base_price ?? unit.price)

  return Math.abs(unit.price - target) > 0.001 ? target : null
}

/**
 * Precio que le toca a un ítem cuando cambia su cantidad.
 *
 * Es la contraparte de `autoTierTarget` para una sola línea: no mira cajas ni
 * decide si hay cambio, solo responde "con esta cantidad, ¿a cuánto va?".
 * Devuelve el precio intacto cuando no le corresponde tocarlo: ítem vendido por
 * caja, o precio pactado a mano por la cajera (`forcedPriceTier`). Sin ese
 * segundo guard, subir la cantidad de una línea con precio forzado recalculaba
 * el escalón y pisaba el trato, dejando la fila marcada como "forzada" con otro
 * precio.
 */
export function priceForQty(item: CartItem, qty: number): number {
  if (item.unit_kind === 'package') return item.price
  if (item.forcedPriceTier) return item.price

  const base = item.base_price ?? item.price
  if (!item.prices?.length) return base

  const qualifying = item.prices
    .filter((t) => t.min_quantity <= qty)
    .sort((a, b) => b.min_quantity - a.min_quantity)

  return qualifying.length ? qualifying[0].unit_price : base
}

/** Map clave → nombre del escalón forzado, derivado del carrito (fuente única). */
export function forcedTierMap(cart: CartItem[]): Map<string, string> {
  const m = new Map<string, string>()
  for (const item of cart) if (item.forcedPriceTier) m.set(cartKeyOf(item), item.forcedPriceTier)
  return m
}
