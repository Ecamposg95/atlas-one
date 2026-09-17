import type { CartItem } from '../../types/sales'

export interface CartGroup {
  key: string             // clave de render: variant_id de la pieza, o product_id si no hay variante
  productId: string
  unit: CartItem | null
  cajas: CartItem[]
}

/**
 * Agrupa el carrito para el render del ticket (una fila por grupo).
 *
 * Las piezas se agrupan por `variant_id` cuando existe: dos tallas del mismo
 * producto son líneas independientes. Antes se agrupaba solo por
 * `product_id`, así que la talla agregada más reciente pisaba a la anterior
 * en `map.set` — desaparecía del ticket (no se podía editar ni quitar) pero
 * `subtotal()/total()` sí la seguían cobrando porque suman el carrito crudo.
 *
 * Las cajas no llevan `variant_id` (productos con variantes no usan cajas,
 * fuera de alcance) y siempre se cuelgan del grupo sin variante de su
 * `product_id`.
 */
export function groupCart(cart: CartItem[]): CartGroup[] {
  const map = new Map<string, CartGroup>()
  for (const item of cart) {
    if (item.cart_key?.includes('::caja::')) {
      const key = item.product_id
      const g = map.get(key) ?? { key, productId: item.product_id, unit: null, cajas: [] }
      g.cajas.push(item)
      map.set(key, g)
    } else {
      const key = item.variant_id ?? item.product_id
      const g = map.get(key) ?? { key, productId: item.product_id, unit: null, cajas: [] }
      g.unit = item
      map.set(key, g)
    }
  }
  return [...map.values()]
}
