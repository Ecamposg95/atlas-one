import { describe, it, expect } from 'vitest'

import { esFilaPrincipal, planIdentidadDeFila } from '../variantEdit'
import type { Product } from '../../../types/products'

const base: Product = {
  id: 'p1', sku: 'PLY-CH', name: 'Playera', description: null, brand_id: null, brand_name: null,
  department: null, department_name: null, unit: 'pza', cost: 60, price: 100, stock: 0,
  image_url: null, is_active: true, barcode: '111',
  variants: [
    { id: 'v-ch', product_id: 'p1', sku: 'PLY-CH', variant_name: 'Ch', price: 100, cost: 60, barcode: '111' },
    { id: 'v-m', product_id: 'p1', sku: 'PLY-M', variant_name: 'M', price: 100, cost: 60, barcode: '222' },
  ],
}
const sinVariantes: Product = { ...base, sku: 'GOR', barcode: null, variants: [] }

describe('esFilaPrincipal', () => {
  it('la primera variante viva es la principal', () => {
    expect(esFilaPrincipal(base, 'v-ch')).toBe(true)
    expect(esFilaPrincipal(base, 'v-m')).toBe(false)
  })
  it('sin variantes o sin variant_id la fila es la del producto', () => {
    expect(esFilaPrincipal(sinVariantes, undefined)).toBe(true)
    expect(esFilaPrincipal(base, undefined)).toBe(true)
  })
})

describe('planIdentidadDeFila', () => {
  it('en la fila principal el SKU y el código siguen yendo al producto', () => {
    const plan = planIdentidadDeFila(base, 'v-ch', { sku: 'PLY-CH2', barcode: '999' })
    expect(plan.esPrincipal).toBe(true)
    expect(plan.productPatch).toEqual({ sku: 'PLY-CH2', barcode: '999' })
    expect(plan.variantPatch).toBeNull()
  })

  it('sin variantes se comporta igual que antes: todo al producto', () => {
    const plan = planIdentidadDeFila(sinVariantes, undefined, { sku: 'GOR2', barcode: null })
    expect(plan.esPrincipal).toBe(true)
    expect(plan.productPatch).toEqual({ sku: 'GOR2', barcode: null })
    expect(plan.variantPatch).toBeNull()
  })

  it('en una talla NO principal el SKU y el código van a la variante, nunca al producto', () => {
    const plan = planIdentidadDeFila(base, 'v-m', { sku: 'PLY-M2', barcode: '333' })
    expect(plan.esPrincipal).toBe(false)
    expect(plan.productPatch).toEqual({})
    expect(plan.variantPatch).toEqual({ variantId: 'v-m', patch: { sku: 'PLY-M2', barcode: '333' } })
  })

  it('si la talla no principal no cambió su identidad, no se manda nada a la variante', () => {
    const plan = planIdentidadDeFila(base, 'v-m', { sku: 'PLY-M', barcode: '222' })
    expect(plan.productPatch).toEqual({})
    expect(plan.variantPatch).toBeNull()
  })

  it('solo viaja el campo que cambió', () => {
    const plan = planIdentidadDeFila(base, 'v-m', { sku: 'PLY-M', barcode: '444' })
    expect(plan.variantPatch).toEqual({ variantId: 'v-m', patch: { barcode: '444' } })
  })

  it('borrar el código de barras de una talla manda null, no cadena vacía', () => {
    const plan = planIdentidadDeFila(base, 'v-m', { sku: 'PLY-M', barcode: '' })
    expect(plan.variantPatch).toEqual({ variantId: 'v-m', patch: { barcode: null } })
  })

  it('un variant_id que ya no existe se trata como fila principal', () => {
    const plan = planIdentidadDeFila(base, 'v-retirada', { sku: 'X', barcode: 'Y' })
    expect(plan.esPrincipal).toBe(true)
    expect(plan.productPatch).toEqual({ sku: 'X', barcode: 'Y' })
  })
})
