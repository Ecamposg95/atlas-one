import { describe, it, expect } from 'vitest'

import { groupCart } from '../cartGroups'
import type { CartItem } from '../../../types/sales'

// El ticket agrupaba solo por product_id: la segunda talla agregada pisaba a
// la primera en el Map y desaparecía de la pantalla (no se podía editar ni
// quitar), aunque el total sí la seguía cobrando.

const pieza = (over: Partial<CartItem> = {}): CartItem => ({
  product_id: 'p1', sku: 'PLY', name: 'Playera', price: 100, quantity: 1, discount: 0, subtotal: 100, ...over,
})

describe('groupCart', () => {
  it('dos piezas con variant_id distinto y mismo product_id -> dos grupos', () => {
    const talla_s = pieza({ variant_id: 'v-s', cart_key: 'v-s', sku: 'PLY-S' })
    const talla_m = pieza({ variant_id: 'v-m', cart_key: 'v-m', sku: 'PLY-M' })
    const groups = groupCart([talla_s, talla_m])
    expect(groups).toHaveLength(2)
    expect(groups.map((g) => g.key).sort()).toEqual(['v-m', 'v-s'])
    expect(groups.every((g) => g.unit !== null)).toBe(true)
  })

  it('una pieza + una caja del mismo producto sin variantes -> un grupo con unit y una caja', () => {
    const unit = pieza({ quantity: 3 })
    const caja = pieza({
      cart_key: 'p1::caja::t1', quantity: 1, price: 1000, subtotal: 1000,
    })
    const groups = groupCart([unit, caja])
    expect(groups).toHaveLength(1)
    expect(groups[0].key).toBe('p1')
    expect(groups[0].unit).toBe(unit)
    expect(groups[0].cajas).toEqual([caja])
  })

  it('sin variant_id se comporta como antes: un grupo por product_id', () => {
    const a = pieza({ product_id: 'p1' })
    const b = pieza({ product_id: 'p2' })
    const groups = groupCart([a, b])
    expect(groups).toHaveLength(2)
    expect(groups.map((g) => g.key).sort()).toEqual(['p1', 'p2'])
  })
})
