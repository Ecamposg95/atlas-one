import { describe, it, expect, vi, afterEach } from 'vitest'

import { resumenDesdeProducto, vibrar } from '../sesion'

describe('vibrar', () => {
  afterEach(() => { vi.unstubAllGlobals() })
  it('usa el patrón corto para ok y el triple para aviso, y no truena sin vibrate', () => {
    const vibrate = vi.fn()
    vi.stubGlobal('navigator', { vibrate })
    vibrar('ok'); vibrar('aviso')
    expect(vibrate).toHaveBeenNthCalledWith(1, 60)
    expect(vibrate).toHaveBeenNthCalledWith(2, [60, 60, 60])
    vi.stubGlobal('navigator', {})
    expect(() => vibrar('ok')).not.toThrow()
  })
})

describe('resumenDesdeProducto', () => {
  it('toma la talla elegida del buscador y el nombre de venta de la variante', () => {
    const r = resumenDesdeProducto(
      { id: 'p', name: 'Playera', brand_name: 'Zegna', image_url: null, department_name: 'Playeras' } as never,
      { id: 'v1', sku: 'ZEG-M', barcode: null, size: 'M', color: 'Rojo', sale_name: 'Zegna · Playera · Rojo, Talla M' } as never,
    )
    expect(r).toEqual({
      variant_id: 'v1', nombre: 'Zegna · Playera · Rojo, Talla M', marca: 'Zegna', talla: 'M', color: 'Rojo',
      sku: 'ZEG-M', barcode: null, foto: null, departamento: 'Playeras',
    })
  })
})
