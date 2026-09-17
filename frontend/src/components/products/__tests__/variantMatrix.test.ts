import { describe, it, expect } from 'vitest'

import { buildVariantRows, parseList, splitPrincipal, toExtraVariants } from '../variantMatrix'

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
    prev[0].sku = 'MI-SKU'
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
