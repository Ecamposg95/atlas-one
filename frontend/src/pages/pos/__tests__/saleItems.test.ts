import { describe, it, expect } from 'vitest'

import { buildSaleItems } from '../saleItems'
import type { CartItem } from '../../../types/sales'

// El renglon de venta debe llevar la variante elegida: sin `variant_id` el
// backend resuelve por SKU y una boutique vende la talla equivocada.

const pieza = (over: Partial<CartItem> = {}): CartItem => ({
  product_id: 'p1', sku: 'PLY-M', name: 'Playera', price: 120, quantity: 2, discount: 0, subtotal: 240,
  variant_id: 'v-m', variant_label: 'Rojo / M', cart_key: 'v-m', ...over,
})

describe('buildSaleItems', () => {
  it('manda variant_id y sku por pieza', () => {
    const [it] = buildSaleItems([pieza()], 0)
    expect(it.variant_id).toBe('v-m')
    expect(it.sku).toBe('PLY-M')
    expect(it.quantity).toBe(2)
    expect(it.unit_price).toBe(120)
  })

  it('aplica el descuento global al precio unitario', () => {
    const [it] = buildSaleItems([pieza()], 10)
    expect(it.unit_price).toBeCloseTo(108)
    expect(it.subtotal).toBeCloseTo(216)
  })

  it('expande una caja a piezas y conserva la variante', () => {
    const caja = pieza({
      cart_key: 'p1::caja::t9', quantity: 1, price: 1000,
      prices: [{ id: 't9', price_name: 'Caja', min_quantity: 12, unit_price: 100, linked_package_id: null }],
    })
    const [it] = buildSaleItems([caja], 0)
    expect(it.quantity).toBe(12)
    expect(it.unit_price).toBe(100)
    expect(it.variant_id).toBe('v-m')
  })

  it('sin variant_id sigue funcionando por sku (tiendas sin variantes)', () => {
    const [it] = buildSaleItems([pieza({ variant_id: undefined, cart_key: undefined })], 0)
    expect(it.variant_id).toBeUndefined()
    expect(it.sku).toBe('PLY-M')
  })
})
