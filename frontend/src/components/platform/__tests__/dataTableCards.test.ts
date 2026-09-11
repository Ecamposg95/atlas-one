import { describe, it, expect } from 'vitest'
import { cardColumns } from '../dataTableCards'

// Spec 2026-09-09 §3.3: bajo 640 px cada fila es una tarjeta con la primera
// columna como titular y máximo 3 secundarias. `DataTable` es la tabla de 8
// páginas de /platform; la partición se prueba pura, sin renderizar.
const col = (key: string) => ({ key, label: key, accessor: () => null })

describe('cardColumns', () => {
  it('la primera columna es el titular y las siguientes 3 son secundarias', () => {
    const { primary, secondary } = cardColumns([col('a'), col('b'), col('c'), col('d'), col('e')])
    expect(primary.key).toBe('a')
    expect(secondary.map((c) => c.key)).toEqual(['b', 'c', 'd'])
  })

  it('respeta un máximo distinto', () => {
    const { secondary } = cardColumns([col('a'), col('b'), col('c')], 1)
    expect(secondary.map((c) => c.key)).toEqual(['b'])
  })

  it('con una sola columna no hay secundarias', () => {
    const { primary, secondary } = cardColumns([col('solo')])
    expect(primary.key).toBe('solo')
    expect(secondary).toEqual([])
  })

  it('sin columnas lanza un error claro', () => {
    expect(() => cardColumns([])).toThrow('DataTable sin columnas')
  })

  it('una columna "actions" al final se separa como actions y no entra en secondary', () => {
    const { primary, secondary, actions } = cardColumns([
      col('a'), col('b'), col('c'), col('d'), col('actions'),
    ])
    expect(primary.key).toBe('a')
    expect(secondary.map((c) => c.key)).toEqual(['b', 'c', 'd'])
    expect(actions?.key).toBe('actions')
  })

  it('sin columna "actions" el resultado no cambia', () => {
    const { primary, secondary, actions } = cardColumns([col('a'), col('b'), col('c')])
    expect(primary.key).toBe('a')
    expect(secondary.map((c) => c.key)).toEqual(['b', 'c'])
    expect(actions).toBeUndefined()
  })
})
