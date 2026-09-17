import { describe, it, expect } from 'vitest'

import { groupVariants, needsPicker, pickVariantForCart } from '../variantPicker'
import type { Product, ProductVariant } from '../../../types/products'

const v = (id: string, color: string | null, size: string | null, stock: number): ProductVariant => ({
  id, product_id: 'p1', sku: `PLY-${id}`, color, size, variant_name: [color, size].filter(Boolean).join(' / ') || 'Estándar',
  price: 120, cost: 60, stock_total: stock,
})
const base: Product = {
  id: 'p1', sku: 'PLY-s', name: 'Playera', description: null, brand_id: null, brand_name: null, department: null,
  department_name: null, unit: 'pza', cost: 60, price: 100, stock: 0, stock_total: 3, image_url: null, is_active: true,
  variants: [v('s', 'Rojo', 'S', 3), v('m', 'Rojo', 'M', 0), v('lm', 'Negro', 'M', 5)],
}

describe('needsPicker', () => {
  it('sí con varias variantes y sin empate de código', () => {
    expect(needsPicker({ ...base, matched_variant_id: null })).toBe(true)
  })
  it('sí con el payload real de /pos/search por texto (el backend omite el empate)', () => {
    // Lo que devuelve search_products_pos al teclear "playera": campos
    // aplanados de la primera variante viva y matched_variant_id en null.
    const payload = { ...base, sku: 'PLY-s', price: 100, matched_variant_id: null }
    expect(needsPicker(payload)).toBe(true)
  })
  it('no cuando el escaneo ya resolvió la variante', () => {
    expect(needsPicker({ ...base, matched_variant_id: 'm' })).toBe(false)
  })
  it('no con una sola variante', () => {
    expect(needsPicker({ ...base, variants: [v('s', null, null, 3)], matched_variant_id: null })).toBe(false)
  })
})

describe('groupVariants', () => {
  it('lista colores y tallas en orden de aparición y localiza la celda', () => {
    const g = groupVariants(base.variants!)
    expect(g.colors).toEqual(['Rojo', 'Negro'])
    expect(g.sizes).toEqual(['S', 'M'])
    expect(g.at('Negro', 'M')?.id).toBe('lm')
    expect(g.at('Negro', 'S')).toBeUndefined()
  })
})

describe('pickVariantForCart', () => {
  it('deja el producto listo para addToCart con los datos de la talla', () => {
    const p = pickVariantForCart(base, base.variants![2])
    expect(p.matched_variant_id).toBe('lm')
    expect(p.sku).toBe('PLY-lm')
    expect(Number(p.stock_total)).toBe(5)
    expect(Number(p.price)).toBe(120)
  })
})
