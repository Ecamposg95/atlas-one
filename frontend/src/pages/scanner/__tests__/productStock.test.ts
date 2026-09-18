import { describe, it, expect } from 'vitest'

import { currentStock, matchedVariant, parseTierPrice, withSelectedVariant } from '../productStock'
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

// El conteo del scanner escribia el kardex de variants[0]: escanear la talla
// XL y contar anaquel ajustaba la talla S.
const playera = (): Product => ({
  id: 'p1', sku: 'PLY-M', name: 'Playera', description: null, brand_id: null, brand_name: null,
  department: null, department_name: null, unit: 'pza', cost: 60, price: 120, stock: 0,
  stock_total: 7, image_url: null, is_active: true, matched_variant_id: 'v-m',
  variants: [
    { id: 'v-s', product_id: 'p1', sku: 'PLY-S', variant_name: 'Rojo / S', price: 100, cost: 50, stock_total: '100' },
    { id: 'v-m', product_id: 'p1', sku: 'PLY-M', variant_name: 'Rojo / M', price: 120, cost: 60, stock_total: '7' },
  ],
  stock_levels: [{ branch_id: 20, qty_on_hand: 7, is_active: true }],
})

describe('matchedVariant', () => {
  it('devuelve la variante que empató el escaneo', () => {
    expect(matchedVariant(playera())?.id).toBe('v-m')
  })
  it('cae a la primera si el backend no dijo cuál', () => {
    expect(matchedVariant({ ...playera(), matched_variant_id: null })?.id).toBe('v-s')
  })
  it('null sin variantes', () => {
    expect(matchedVariant({ ...playera(), variants: [] })).toBeNull()
  })
})

describe('currentStock por variante', () => {
  it('usa stock_total de la variante empatada antes que stock_levels', () => {
    const p = playera()
    p.stock_levels = [{ branch_id: 20, qty_on_hand: 100, is_active: true }]
    expect(currentStock(p, 20)).toBe(7)
  })
})

// Sin código de barras el backend no empata ninguna talla y manda aplanada la
// principal: el scanner solo dejaba ver y ajustar la Ch. `withSelectedVariant`
// es lo que deja al cajero pararse en la M sin volver a escanear.
describe('withSelectedVariant', () => {
  const p = {
    id: 'p1', name: 'Blusa', sku: 'BL-CH', price: 300, barcode: null, stock_total: 9,
    variants: [
      { id: 'ch', sku: 'BL-CH', variant_name: 'Ch', size: 'Ch', price: 300, stock_total: 9, barcode: null },
      { id: 'm', sku: 'BL-M', variant_name: 'M', size: 'M', price: 350, stock_total: 2, barcode: '750' },
    ],
  } as unknown as Product

  it('aplana la talla elegida sobre el producto', () => {
    const vista = withSelectedVariant(p, 'm')
    expect(vista.matched_variant_id).toBe('m')
    expect(vista.sku).toBe('BL-M')
    expect(Number(vista.price)).toBe(350)
    expect(Number(vista.stock_total)).toBe(2)
    expect(vista.barcode).toBe('750')
  })

  it('el conteo pasa a ser el de la talla elegida', () => {
    expect(currentStock(withSelectedVariant(p, 'm'), null)).toBe(2)
    expect(currentStock(withSelectedVariant(p, 'ch'), null)).toBe(9)
  })

  it('sin id o con un id desconocido devuelve el producto tal cual', () => {
    expect(withSelectedVariant(p, null)).toBe(p)
    expect(withSelectedVariant(p, 'zzz')).toBe(p)
  })

  // El ticket cobra el `price_override` de la sucursal; la ficha del scanner
  // mostraba el precio base y el cajero cotizaba de más (o de menos).
  it('aplana el precio de la sucursal cuando la talla trae override', () => {
    const conOverride = {
      ...p,
      variants: [p.variants![0], { ...p.variants![1], effective_price: 299 }],
    } as unknown as Product
    expect(Number(withSelectedVariant(conOverride, 'm').price)).toBe(299)
  })

  it('sin override sigue aplanando el precio base', () => {
    expect(Number(withSelectedVariant(p, 'm').price)).toBe(350)
  })

  it('no toca los escalones del producto (son del producto, no de la talla)', () => {
    const conEscalones = { ...p, prices: [{ id: 't1', price_name: 'Mayoreo', min_quantity: 3, unit_price: 280, linked_package_id: null }] } as unknown as Product
    expect(withSelectedVariant(conEscalones, 'm').prices).toEqual(conEscalones.prices)
  })
})
