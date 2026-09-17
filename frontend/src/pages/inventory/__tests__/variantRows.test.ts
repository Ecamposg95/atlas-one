import { describe, it, expect } from 'vitest'

import { expandVariantRows } from '../variantRows'
import type { Product } from '../../../types/products'

const playera: Product = {
  id: 'p1', sku: 'PLY-S', name: 'Playera', description: null, brand_id: null, brand_name: null, department: null,
  department_name: null, unit: 'pza', cost: 60, price: 100, stock: 0, stock_total: 3, image_url: null, is_active: true,
  variants: [
    { id: 'v-s', product_id: 'p1', sku: 'PLY-S', variant_name: 'Rojo / S', price: 100, cost: 60, stock_total: '3' },
    { id: 'v-m', product_id: 'p1', sku: 'PLY-M', variant_name: 'Rojo / M', price: 100, cost: 60, stock_total: '0' },
  ],
}
const gorra: Product = { ...playera, id: 'p2', sku: 'GOR', name: 'Gorra', stock_total: 9,
  variants: [{ id: 'v-g', product_id: 'p2', sku: 'GOR', variant_name: 'Estándar', price: 50, cost: 20, stock_total: '9' }] }

describe('expandVariantRows', () => {
  it('un renglón por variante con etiqueta y existencia propia', () => {
    const rows = expandVariantRows([playera, gorra])
    expect(rows.map((r) => r.label)).toEqual(['Playera · Rojo / S', 'Playera · Rojo / M', 'Gorra'])
    expect(rows.map((r) => r.qty)).toEqual([3, 0, 9])
    expect(rows[1].variant.id).toBe('v-m')
  })
  it('producto sin variantes genera un renglón con lo aplanado', () => {
    const rows = expandVariantRows([{ ...gorra, variants: [] }])
    expect(rows).toHaveLength(1)
    expect(rows[0].qty).toBe(9)
    expect(rows[0].variant.id).toBe('p2')
  })
})
