import type { CartItem } from '../../types/sales'

export interface SaleItemPayload {
  product_id: string
  variant_id?: string
  sku: string
  name: string
  unit_price: number
  price: number
  quantity: number
  discount: number
  subtotal: number
}

/**
 * Renglones que se mandan a POST /api/sales.
 *
 * Los ítems de caja (cart_key con '::caja::') se expanden a piezas al precio
 * unitario del escalón. El descuento global se multiplica en cada precio
 * unitario (el guard server-side evalúa sobre el precio final). `variant_id`
 * viaja siempre que se conozca: es lo que hace que una boutique cobre y
 * descuente la talla elegida y no la primera del producto.
 */
export function buildSaleItems(cart: CartItem[], globalDiscount: number): SaleItemPayload[] {
  const gdFactor = 1 - (globalDiscount || 0) / 100
  return cart.map((c) => {
    const base = {
      product_id: c.product_id,
      ...(c.variant_id ? { variant_id: c.variant_id } : {}),
      sku: c.sku,
      name: c.name,
      discount: c.discount,
    }
    if (c.cart_key?.includes('::caja::')) {
      const tierId = c.cart_key.split('::caja::')[1]
      const cajaTier = c.prices?.find((p) => p.id === tierId)
      if (cajaTier && cajaTier.min_quantity > 0) {
        const totalPiezas = c.quantity * cajaTier.min_quantity
        const unitPrice = cajaTier.unit_price * gdFactor
        return { ...base, unit_price: unitPrice, price: unitPrice, quantity: totalPiezas,
                 subtotal: totalPiezas * unitPrice * (1 - c.discount / 100) }
      }
    }
    const unitPrice = c.price * gdFactor
    return { ...base, unit_price: unitPrice, price: unitPrice, quantity: c.quantity,
             subtotal: c.quantity * unitPrice * (1 - c.discount / 100) }
  })
}
