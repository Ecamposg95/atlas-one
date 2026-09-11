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

/** Map clave → nombre del escalón forzado, derivado del carrito (fuente única). */
export function forcedTierMap(cart: CartItem[]): Map<string, string> {
  const m = new Map<string, string>()
  for (const item of cart) if (item.forcedPriceTier) m.set(cartKeyOf(item), item.forcedPriceTier)
  return m
}
