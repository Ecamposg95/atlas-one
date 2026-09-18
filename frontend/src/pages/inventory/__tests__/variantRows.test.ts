import { describe, it, expect } from 'vitest'

import { expandVariantRows, grupoDeVariantes } from '../variantRows'
import type { Product, ProductVariant } from '../../../types/products'

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
const camisa: Product = { ...playera, id: 'p3', sku: 'CAM', name: 'Camisa', stock_total: 5,
  variants: [{ id: 'v-c', product_id: 'p3', sku: 'CAM-S', variant_name: 'Rojo / S', barcode: '7501234567890', price: 200, cost: 120, stock_total: '5' }] }

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
  it('con una sola variante, aunque tenga nombre, la etiqueta es el nombre del producto a secas', () => {
    const rows = expandVariantRows([camisa])
    expect(rows).toHaveLength(1)
    expect(rows[0].label).toBe('Camisa')
    expect(rows[0].sku).toBe('CAM-S')
    expect(rows[0].barcode).toBe('7501234567890')
  })
})

describe('precio por renglón', () => {
  it('cada renglón conserva el precio de su propia talla, no el de la principal', () => {
    const conPrecios: Product = {
      ...playera,
      price: 100, // el aplanado del backend = la principal
      variants: [
        { id: 'v-s', product_id: 'p1', sku: 'PLY-S', variant_name: 'S', price: 100, cost: 60, stock_total: '3' },
        { id: 'v-m', product_id: 'p1', sku: 'PLY-M', variant_name: 'M', price: 180, cost: 60, stock_total: '0' },
      ],
    }
    const rows = expandVariantRows([conPrecios])
    expect(rows.map((r) => r.variant.price)).toEqual([100, 180])
  })
})

describe('grupoDeVariantes', () => {
  const v = (extra: Partial<ProductVariant>): ProductVariant =>
    ({ id: 'x', product_id: 'p', sku: 'X', price: 1, cost: 1, ...extra })

  it('sin ningún color, la palabra es "tallas"', () => {
    expect(grupoDeVariantes([v({ size: 'Ch' }), v({ size: 'M' })])).toBe('tallas')
  })
  it('sin ninguna talla, la palabra es "colores"', () => {
    expect(grupoDeVariantes([v({ color: 'Rojo' }), v({ color: 'Azul' })])).toBe('colores')
  })
  it('con color y talla mezclados, la palabra genérica es "variantes"', () => {
    expect(grupoDeVariantes([v({ color: 'Rojo', size: 'Ch' }), v({ color: 'Rojo', size: 'M' })])).toBe('variantes')
  })
  it('sin atributos cae en "variantes"', () => {
    expect(grupoDeVariantes([v({}), v({})])).toBe('variantes')
  })
  it('el color vacío no cuenta como color', () => {
    expect(grupoDeVariantes([v({ color: '', size: 'Ch' }), v({ color: null, size: 'M' })])).toBe('tallas')
  })
})
