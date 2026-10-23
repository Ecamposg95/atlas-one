import { describe, expect, it } from 'vitest'

import type { Product } from '../../../types/products'
import { cambiosFicha, formDesde, type FormFicha } from './ficha'

const base: FormFicha = {
  name: 'Playera', brand_id: 'b1', model: 'Monogram', description: 'Algodón', department_id: 'd1',
  size: 'M', color: 'Negro', barcode: '7501', price: '1200', cost: '600',
}

describe('cambiosFicha', () => {
  it('sin cambios no genera ninguna llamada', () => {
    expect(cambiosFicha(base, { ...base })).toEqual({ producto: null, variante: null, error: null })
  })

  it('solo el producto cuando cambian nombre, marca o departamento', () => {
    const r = cambiosFicha(base, { ...base, name: ' Playera básica ', brand_id: '', department_id: 'd2' })
    expect(r.producto).toEqual({ name: 'Playera básica', brand_id: null, department_id: 'd2' })
    expect(r.variante).toBeNull()
    expect(r.error).toBeNull()
  })

  it('solo la variante cuando cambian talla, código, precio o costo', () => {
    const r = cambiosFicha(base, { ...base, size: 'G', barcode: '', price: '1300.50', cost: '600.00' })
    expect(r.producto).toBeNull()
    expect(r.variante).toEqual({ size: 'G', barcode: null, price: 1300.5 })
  })

  it('"100.00" y "100" son el mismo precio', () => {
    expect(cambiosFicha({ ...base, price: '100.00' }, { ...base, price: '100' }).variante).toBeNull()
  })

  it('precio o costo en blanco se dejan como estaban', () => {
    expect(cambiosFicha(base, { ...base, price: '', cost: ' ' })).toEqual({ producto: null, variante: null, error: null })
  })

  it('el nombre vacío y los números inválidos frenan el guardado', () => {
    expect(cambiosFicha(base, { ...base, name: '  ' }).error).toMatch(/nombre/)
    expect(cambiosFicha(base, { ...base, price: '-5' }).error).toMatch(/precio/)
    expect(cambiosFicha(base, { ...base, cost: 'abc' }).error).toMatch(/costo/)
  })
})

describe('formDesde', () => {
  const producto = {
    id: 'p1', name: 'Playera', brand_id: 'b1', model: 'Monogram', description: null,
    department: { id: 'd1', name: 'Playeras' }, price: 1000, cost: 500,
    variants: [
      { id: 'v1', product_id: 'p1', sku: 'A-1', size: 'Ch', color: 'Negro', barcode: '1', price: 1000, cost: 500 },
      { id: 'v2', product_id: 'p1', sku: 'A-2', size: 'M', color: null, barcode: null, price: 1100, cost: 550 },
    ],
  } as unknown as Product

  it('toma los datos del producto y de la talla pedida', () => {
    expect(formDesde(producto, 'v2')).toEqual({
      name: 'Playera', brand_id: 'b1', model: 'Monogram', description: '', department_id: 'd1',
      size: 'M', color: '', barcode: '', price: '1100', cost: '550',
    })
  })

  it('sin la talla en el producto cae al precio y costo base', () => {
    expect(formDesde(producto, 'v9')).toMatchObject({ size: '', price: '1000', cost: '500' })
  })
})
