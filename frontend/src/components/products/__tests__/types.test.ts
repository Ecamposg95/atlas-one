import { describe, it, expect } from 'vitest'
import { emptyPackagingRow } from '../types'

describe('types del formulario', () => {
  it('un empaque nuevo es una caja de 1 pieza a $0', () => {
    expect(emptyPackagingRow()).toEqual({ name: 'Caja', barcode: '', units_per_package: 1, package_price: 0 })
  })
})
