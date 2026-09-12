import { describe, it, expect } from 'vitest'
import { autoTierTarget, cajaTierOf, cartKeyOf, forcedTierMap, priceForQty } from '../cartTiers'
import type { CartItem } from '../../../types/sales'

const tiers = [
  { id: '1', price_name: 'Menudeo', min_quantity: 1, unit_price: 15 },
  { id: '2', price_name: 'Mayoreo', min_quantity: 6, unit_price: 13 },
  { id: '3', price_name: 'Caja', min_quantity: 12, unit_price: 10.83 },
]
const unit = (over: Partial<CartItem> = {}): CartItem => ({
  product_id: 'p1', cart_key: 'p1', sku: 'M-1', name: 'Mantequilla chica',
  price: 15, base_price: 15, quantity: 1, discount: 0, subtotal: 15,
  prices: tiers as CartItem['prices'],
  ...over,
} as CartItem)

describe('autoTierTarget — precio automático por cantidad total', () => {
  it('sin escalones no propone nada', () => {
    expect(autoTierTarget(unit({ prices: [] }), 0)).toBeNull()
  })
  it('1 pieza queda en menudeo (ya correcto → null)', () => {
    expect(autoTierTarget(unit({ quantity: 1, price: 15 }), 0)).toBeNull()
  })
  it('6 piezas proponen mayoreo', () => {
    expect(autoTierTarget(unit({ quantity: 6, price: 15 }), 0)).toBe(13)
  })
  it('las cajas cuentan como sus piezas: 1 caja + 1 pieza = 13 piezas → precio de caja', () => {
    expect(autoTierTarget(unit({ quantity: 1, price: 15 }), 1)).toBe(10.83)
  })
  it('un precio FORZADO nunca se toca, sin importar la cantidad (regla del dueño: caja sin cantidad es lo normal)', () => {
    expect(autoTierTarget(unit({ quantity: 1, price: 10.83, forcedPriceTier: 'Caja' }), 0)).toBeNull()
    expect(autoTierTarget(unit({ quantity: 20, price: 15, forcedPriceTier: 'Menudeo' }), 0)).toBeNull()
  })
  it('cajaForcedByBulk tampoco se toca', () => {
    expect(autoTierTarget(unit({ quantity: 20, price: 15, cajaForcedByBulk: true }), 0)).toBeNull()
  })
  it('sin escalón que empate cae al precio base', () => {
    const t = [{ id: '2', price_name: 'Mayoreo', min_quantity: 6, unit_price: 13 }]
    expect(autoTierTarget(unit({ quantity: 2, price: 13, base_price: 15, prices: t as CartItem['prices'] }), 0)).toBe(15)
  })
})

describe('forcedTierMap — el Map se deriva del carrito, no de un estado aparte', () => {
  it('solo incluye ítems con forcedPriceTier', () => {
    const m = forcedTierMap([unit(), unit({ cart_key: 'p2', product_id: 'p2', forcedPriceTier: 'Caja' })])
    expect(m.size).toBe(1)
    expect(m.get('p2')).toBe('Caja')
  })
  it('usa cart_key y cae a product_id si no hay cart_key', () => {
    const m = forcedTierMap([unit({ cart_key: undefined, product_id: 'p9', forcedPriceTier: 'libre' })])
    expect(m.get('p9')).toBe('libre')
  })
})

describe('cartKeyOf — la misma clave que usa el carrito', () => {
  it('prefiere cart_key', () => {
    expect(cartKeyOf(unit({ cart_key: 'p1::caja::3', product_id: 'p1' }))).toBe('p1::caja::3')
  })
  it('cae a product_id cuando no hay cart_key', () => {
    expect(cartKeyOf(unit({ cart_key: undefined, product_id: 'p7' }))).toBe('p7')
  })
})

describe('cajaTierOf — el primer escalon cuyo nombre contiene "caja"', () => {
  it('lo encuentra sin importar mayusculas', () => {
    const t = [{ id: '9', price_name: 'CAJA de 12', min_quantity: 12, unit_price: 10 }]
    expect(cajaTierOf(unit({ prices: t as CartItem['prices'] }))?.id).toBe('9')
  })
  it('devuelve el PRIMERO que coincide, no el mas barato', () => {
    const t = [
      { id: 'a', price_name: 'Media caja', min_quantity: 6, unit_price: 13 },
      { id: 'b', price_name: 'Caja completa', min_quantity: 12, unit_price: 10 },
    ]
    expect(cajaTierOf(unit({ prices: t as CartItem['prices'] }))?.id).toBe('a')
  })
  it('sin escalon de caja devuelve undefined', () => {
    const t = [{ id: '1', price_name: 'Menudeo', min_quantity: 1, unit_price: 15 }]
    expect(cajaTierOf(unit({ prices: t as CartItem['prices'] }))).toBeUndefined()
  })
  it('un item sin escalones no rompe', () => {
    expect(cajaTierOf(unit({ prices: undefined }))).toBeUndefined()
  })
})

describe('priceForQty — cambiar la cantidad NO pisa el precio pactado', () => {
  it('sin forzar, la cantidad manda: 6 piezas caen en mayoreo', () => {
    expect(priceForQty(unit({ quantity: 1, price: 15 }), 6)).toBe(13)
  })
  it('un precio forzado sobrevive al cambio de cantidad (defecto de updateQty)', () => {
    const pactado = unit({ price: 10.83, forcedPriceTier: 'Caja' })
    expect(priceForQty(pactado, 1)).toBe(10.83)
    expect(priceForQty(pactado, 30)).toBe(10.83)
  })
  it('el item vendido por caja conserva su precio de caja', () => {
    expect(priceForQty(unit({ unit_kind: 'package', price: 130 }), 5)).toBe(130)
  })
  it('sin escalon que empate vuelve al precio base', () => {
    const t = [{ id: '2', price_name: 'Mayoreo', min_quantity: 6, unit_price: 13 }]
    expect(priceForQty(unit({ price: 13, base_price: 15, prices: t as CartItem['prices'] }), 2)).toBe(15)
  })
  it('sin escalones se queda en el precio base', () => {
    expect(priceForQty(unit({ prices: [], price: 13, base_price: 15 }), 9)).toBe(15)
  })
})
