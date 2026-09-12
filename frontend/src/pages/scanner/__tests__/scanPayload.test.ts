import { describe, it, expect } from 'vitest'

import { buildDetailsUpdatePayload, buildPriceUpdatePayload } from '../scanPayload'
import type { Product } from '../../../types/products'

// `PUT /api/products/{id}` reemplaza los escalones POR COMPLETO: borra todos
// los ProductPrice de la variante y recrea los que reciba
// (app/routers/products/core.py, "Update Prices (Complete Replacement)").
// Si el scanner manda solo el escalón que tocó el admin, los demás DESAPARECEN
// del catálogo. Estos tests existen para que eso no pueda pasar.

const producto = {
  id: 'p1',
  name: 'Pluma',
  price: 12,
  prices: [
    { id: 't1', price_name: 'Mayoreo', min_quantity: 3, unit_price: 10, linked_package_id: null },
    { id: 't2', price_name: 'Caja', min_quantity: 72, unit_price: 8, linked_package_id: 'pk1' },
  ],
} as unknown as Product

describe('buildPriceUpdatePayload', () => {
  it('manda TODOS los escalones aunque solo se edite uno', () => {
    const payload = buildPriceUpdatePayload(producto, 12, { t1: 9.5 })
    expect(payload.prices).toHaveLength(2)
    expect(payload.prices?.map((p) => p.price_name).sort()).toEqual(['Caja', 'Mayoreo'])
  })

  it('aplica el precio nuevo solo al escalón editado', () => {
    const payload = buildPriceUpdatePayload(producto, 12, { t1: 9.5 })
    const mayoreo = payload.prices?.find((p) => p.price_name === 'Mayoreo')
    const caja = payload.prices?.find((p) => p.price_name === 'Caja')
    expect(mayoreo?.unit_price).toBe(9.5)
    expect(caja?.unit_price).toBe(8)
  })

  it('conserva el vínculo con el empaque', () => {
    // linked_package_id es lo que hace que un escalón sea la CAJA. Perderlo
    // rompe la etiqueta del ticket que acabamos de arreglar.
    const payload = buildPriceUpdatePayload(producto, 12, {})
    const caja = payload.prices?.find((p) => p.price_name === 'Caja')
    expect(caja?.linked_package_id).toBe('pk1')
    expect(caja?.min_quantity).toBe(72)
  })

  it('incluye el precio base', () => {
    expect(buildPriceUpdatePayload(producto, 13.5, {}).price).toBe(13.5)
  })

  it('omite prices cuando el producto no tiene escalones', () => {
    // Mandar `prices: []` BORRARÍA los escalones. Si no hay nada que mandar,
    // el campo no viaja y el backend los deja intactos.
    const sinEscalones = { ...producto, prices: [] } as unknown as Product
    expect(buildPriceUpdatePayload(sinEscalones, 12, {}).prices).toBeUndefined()
  })

  it('ignora ediciones de escalones que no existen en el producto', () => {
    const payload = buildPriceUpdatePayload(producto, 12, { fantasma: 1 })
    expect(payload.prices).toHaveLength(2)
    // sort numérico explícito: el default de JS ordena como texto y pone 10 antes que 8.
    expect(payload.prices?.map((p) => p.unit_price).sort((a, b) => a - b)).toEqual([8, 10])
  })
})

describe('buildDetailsUpdatePayload', () => {
  it('NUNCA manda prices', () => {
    // El PUT borra todos los ProductPrice y recrea los que reciba. Un payload
    // de ficha que arrastre `prices` (aunque sea por copiar el objeto entero
    // del producto) borraría los escalones del catálogo. Este test es el
    // candado: si alguien "simplifica" mandando el producto completo, falla.
    const payload = buildDetailsUpdatePayload(producto, {
      name: 'Pluma Nueva',
      department_id: 'd1',
      brand_id: 'b1',
      barcode: '750123456789',
    })
    expect('prices' in payload).toBe(false)
    expect('packaging_units' in payload).toBe(false)
  })

  it('manda solo los campos que cambiaron', () => {
    const payload = buildDetailsUpdatePayload(producto, { name: 'Pluma Nueva' })
    expect(payload).toEqual({ name: 'Pluma Nueva' })
  })

  it('recorta espacios del nombre y del código', () => {
    const payload = buildDetailsUpdatePayload(producto, {
      name: '  Pluma  ',
      barcode: ' 750123456789 ',
    })
    expect(payload.name).toBe('Pluma')
    expect(payload.barcode).toBe('750123456789')
  })

  it('un código vacío se manda como null para poder borrarlo', () => {
    // Distinto de "no lo toques": null limpia el campo en el backend.
    expect(buildDetailsUpdatePayload(producto, { barcode: '   ' }).barcode).toBeNull()
  })

  it('ignora un nombre vacío en vez de borrarlo', () => {
    // El nombre es obligatorio; vaciarlo dejaría el producto sin identidad.
    expect(buildDetailsUpdatePayload(producto, { name: '   ' })).toEqual({})
  })

  it('permite desasignar departamento y marca con null', () => {
    const payload = buildDetailsUpdatePayload(producto, { department_id: null, brand_id: null })
    expect(payload).toEqual({ department_id: null, brand_id: null })
  })
})
