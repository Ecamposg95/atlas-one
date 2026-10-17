import { describe, it, expect } from 'vitest'
import { EMPTY_PRODUCT_FORM, emptyPackagingRow } from '../types'

describe('types del formulario', () => {
  it('el producto nace llevando inventario', () => {
    expect(EMPTY_PRODUCT_FORM.uses_inventory).toBe(true)
  })
  it('un empaque nuevo es una caja de 1 pieza a $0', () => {
    expect(emptyPackagingRow()).toEqual({ name: 'Caja', barcode: '', units_per_package: 1, package_price: 0 })
  })
})
