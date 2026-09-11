import { describe, it, expect } from 'vitest'
import { autoTierTarget, forcedTierMap } from '../cartTiers'
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
