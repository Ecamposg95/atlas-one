import { describe, it, expect } from 'vitest'

import { buildVariantRows, parseList, splitPrincipal, toExtraVariants, variantFieldErrors } from '../variantMatrix'

describe('parseList', () => {
  it('separa por coma o salto de línea y deduplica sin mayúsculas', () => {
    expect(parseList('Rojo, azul\nROJO ,  Negro ')).toEqual(['Rojo', 'azul', 'Negro'])
  })
  it('vacío es lista vacía', () => {
    expect(parseList('  ')).toEqual([])
  })
})

describe('buildVariantRows', () => {
  it('hace el producto cartesiano con SKU sugerido', () => {
    const rows = buildVariantRows('PLY', ['Rojo'], ['S', 'M'], [])
    expect(rows.map((r) => r.sku)).toEqual(['PLY-ROJO-S', 'PLY-ROJO-M'])
    expect(rows[0].key).toBe('rojo|s')
  })
  it('conserva lo tecleado en filas que ya existían', () => {
    const prev = buildVariantRows('PLY', ['Rojo'], ['S'], [])
    prev[0].barcode = '750'
    // El SKU escrito a mano viaja con `skuTocado` (así lo marca el formulario):
    // sin esa marca se recalcula desde el SKU base en cada regeneración.
    prev[0].sku = 'MI-SKU'
    prev[0].skuTocado = true
    const rows = buildVariantRows('PLY', ['Rojo'], ['S', 'M'], prev)
    expect(rows[0]).toMatchObject({ sku: 'MI-SKU', barcode: '750' })
    expect(rows[1].sku).toBe('PLY-ROJO-M')
  })
  it('quita acentos y espacios del SKU sugerido', () => {
    expect(buildVariantRows('PLY', ['Azul marino'], ['Única'], [])[0].sku).toBe('PLY-AZULMARINO-UNICA')
  })
  it('solo colores o solo tallas también genera filas', () => {
    expect(buildVariantRows('PLY', [], ['S', 'M'], []).map((r) => r.size)).toEqual(['S', 'M'])
    expect(buildVariantRows('PLY', ['Rojo'], [], []).map((r) => r.color)).toEqual(['Rojo'])
  })
})

describe('toExtraVariants', () => {
  it('manda solo lo que trae valor', () => {
    const [row] = buildVariantRows('PLY', ['Rojo'], ['S'], [])
    row.price = ''
    expect(toExtraVariants([row])).toEqual([{ color: 'Rojo', size: 'S', sku: 'PLY-ROJO-S' }])
    row.price = '130'; row.barcode = '750'
    expect(toExtraVariants([row])[0]).toMatchObject({ price: 130, barcode: '750' })
  })
})

describe('splitPrincipal', () => {
  it('sin filas no hay principal', () => {
    expect(splitPrincipal([])).toEqual({ principal: null, extras: [] })
  })
  it('una sola fila es la principal y no deja extras', () => {
    const rows = buildVariantRows('PLY', ['Rojo'], ['S'], [])
    const { principal, extras } = splitPrincipal(rows)
    expect(principal).toMatchObject({ color: 'Rojo', size: 'S' })
    expect(extras).toEqual([])
  })
  it('con tres filas la primera es la principal y el resto son hermanas', () => {
    const rows = buildVariantRows('PLY', ['Rojo'], ['S', 'M', 'L'], [])
    const { principal, extras } = splitPrincipal(rows)
    expect(principal?.size).toBe('S')
    expect(extras.map((r) => r.size)).toEqual(['M', 'L'])
    // El orden de la matriz es el que ve el usuario: no se reordena.
    expect(extras).toEqual(rows.slice(1))
  })
  it('no muta la lista original', () => {
    const rows = buildVariantRows('PLY', ['Rojo'], ['S', 'M'], [])
    splitPrincipal(rows)
    expect(rows).toHaveLength(2)
  })
})

describe('SKU sugerido al cambiar el SKU base', () => {
  it('regenera el SKU de las filas que nadie tocó', () => {
    const prev = buildVariantRows('PLY', [], ['S', 'M'], [])
    const rows = buildVariantRows('PLAYERA', [], ['S', 'M'], prev)
    expect(rows.map((r) => r.sku)).toEqual(['PLAYERA-S', 'PLAYERA-M'])
  })
  it('respeta el SKU que el admin escribió a mano', () => {
    const prev = buildVariantRows('PLY', [], ['S', 'M'], [])
    prev[0] = { ...prev[0], sku: 'MI-SKU', skuTocado: true }
    const rows = buildVariantRows('PLAYERA', [], ['S', 'M'], prev)
    expect(rows.map((r) => r.sku)).toEqual(['MI-SKU', 'PLAYERA-M'])
  })
  it('conserva lo demás de la fila al regenerar', () => {
    const prev = buildVariantRows('PLY', [], ['S'], [])
    prev[0] = { ...prev[0], barcode: '750', price: '99', initial_stock: '4' }
    const [row] = buildVariantRows('PLAYERA', [], ['S'], prev)
    expect(row).toMatchObject({ barcode: '750', price: '99', initial_stock: '4', sku: 'PLAYERA-S' })
  })
})

describe('tallas que ya existen en el producto', () => {
  it('no las vuelve a generar (evita el 409 al agregar variantes)', () => {
    const rows = buildVariantRows('PLY', [], ['Ch', 'M', 'G'], [], [{ size: 'ch' }, { color: null, size: 'M' }])
    expect(rows.map((r) => r.size)).toEqual(['G'])
  })
  it('sin lista de existentes genera todo', () => {
    expect(buildVariantRows('PLY', [], ['Ch', 'M'], []).map((r) => r.size)).toEqual(['Ch', 'M'])
  })
})

describe('existencia inicial por fila', () => {
  it('viaja solo cuando es mayor a cero', () => {
    const [row] = buildVariantRows('PLY', [], ['M'], [])
    expect(toExtraVariants([row])[0].initial_stock).toBeUndefined()
    expect(toExtraVariants([{ ...row, initial_stock: '0' }])[0].initial_stock).toBeUndefined()
    expect(toExtraVariants([{ ...row, initial_stock: '  ' }])[0].initial_stock).toBeUndefined()
    expect(toExtraVariants([{ ...row, initial_stock: '-3' }])[0].initial_stock).toBeUndefined()
    expect(toExtraVariants([{ ...row, initial_stock: '7' }])[0].initial_stock).toBe(7)
  })
  it('las filas nuevas nacen sin existencia', () => {
    expect(buildVariantRows('PLY', [], ['M'], [])[0].initial_stock).toBe('')
  })
})

describe('variantFieldErrors', () => {
  it('renombra las marcas del backend a las claves de la matriz', () => {
    expect(variantFieldErrors({ 'extra_variants.1.sku': 'Requerido', sku: 'Duplicado' }))
      .toEqual({ 'variants.1.sku': 'Requerido', sku: 'Duplicado' })
  })
  it('sin errores devuelve un mapa vacío', () => {
    expect(variantFieldErrors({})).toEqual({})
  })
})
