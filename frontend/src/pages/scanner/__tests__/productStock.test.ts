import { describe, it, expect } from 'vitest'

import { currentStock, parseTierPrice } from '../productStock'
import type { Product } from '../../../types/products'

// Dos bugs que llegaron a producción el 2026-08-29 y que estos tests fijan.

describe('currentStock', () => {
  // BUG 1: la ficha leía `product.stock`, que la API NO manda — ProductRead
  // expone `stock_total` (app/schemas/products.py:199). En runtime era
  // `undefined` -> base 0 -> todo conteo se volvía una ENTRADA y el scanner
  // no podía registrar un faltante de anaquel, solo inflar el inventario.
  it('lee stock_total, que es lo que manda la API', () => {
    expect(currentStock({ stock_total: 40 } as unknown as Product, null)).toBe(40)
  })

  it('acepta stock_total como CADENA', () => {
    // El backend serializa Decimal como string ("40.00"). Number.isFinite lo
    // rechaza y sin convertir se caía otra vez a 0.
    expect(currentStock({ stock_total: '40.00' } as unknown as Product, null)).toBe(40)
  })

  it('prefiere la existencia de la sucursal seleccionada', () => {
    const p = {
      stock_total: 40,
      stock_levels: [
        { branch_id: 1, qty_on_hand: 40 },
        { branch_id: 2, qty_on_hand: 7 },
      ],
    } as unknown as Product
    expect(currentStock(p, 2)).toBe(7)
    expect(currentStock(p, 1)).toBe(40)
  })

  it('si la sucursal no viene en stock_levels usa stock_total', () => {
    const p = { stock_total: 40, stock_levels: [{ branch_id: 1, qty_on_hand: 40 }] } as unknown as Product
    expect(currentStock(p, 99)).toBe(40)
  })

  it('sin dato devuelve 0', () => {
    expect(currentStock({} as Product, null)).toBe(0)
    expect(currentStock({ stock_total: null } as unknown as Product, null)).toBe(0)
  })

  it('NO cae en el campo inexistente `stock` si hay stock_total', () => {
    const p = { stock: 999, stock_total: 12 } as unknown as Product
    expect(currentStock(p, null)).toBe(12)
  })
})

describe('parseTierPrice', () => {
  // BUG 2: el input de escalón hacía Number(e.target.value) directo. Vaciar el
  // campo para reescribirlo da 0, y `edits[id] ?? unit_price` NO rescata el 0
  // (?? solo atrapa null/undefined). El escalón se guardaba en $0.00.
  it('un campo vacío no es un precio', () => {
    expect(parseTierPrice('')).toBeNull()
    expect(parseTierPrice('   ')).toBeNull()
  })

  it('cero no es un precio válido', () => {
    expect(parseTierPrice('0')).toBeNull()
    expect(parseTierPrice('0.00')).toBeNull()
  })

  it('un negativo no es un precio válido', () => {
    expect(parseTierPrice('-5')).toBeNull()
  })

  it('la basura no es un precio', () => {
    expect(parseTierPrice('1.2.3')).toBeNull()
    expect(parseTierPrice('abc')).toBeNull()
  })

  it('acepta un precio normal', () => {
    expect(parseTierPrice('9.5')).toBe(9.5)
    expect(parseTierPrice(' 27 ')).toBe(27)
  })
})
