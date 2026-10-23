import { describe, it, expect, vi, afterEach } from 'vitest'

import { crearCola, debeRedirigirTecla, olvidarUltimoCodigo, resumenDesdeProducto, vibrar } from '../sesion'

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
      variant_id: 'v1', product_id: 'p', marca_id: null, modelo: null, descripcion: null, precio: null, nombre: 'Zegna · Playera · Rojo, Talla M', marca: 'Zegna', talla: 'M', color: 'Rojo',
      sku: 'ZEG-M', barcode: null, foto: null, departamento: 'Playeras',
    })
  })
})

describe('olvidarUltimoCodigo', () => {
  it('solo olvida tras 2 cuadros seguidos sin código', () => {
    expect(olvidarUltimoCodigo(0)).toBe(false)
    expect(olvidarUltimoCodigo(1)).toBe(false)
    expect(olvidarUltimoCodigo(2)).toBe(true)
    expect(olvidarUltimoCodigo(5)).toBe(true)
  })
})

describe('crearCola', () => {
  it('procesa en orden y de a uno aunque lleguen mientras se guarda', async () => {
    const orden: string[] = []
    let enVuelo = 0, maximo = 0
    const fin = vi.fn()
    const cola = crearCola(async (c) => {
      enVuelo++; maximo = Math.max(maximo, enVuelo)
      await new Promise((r) => setTimeout(r, 5))
      orden.push(c); enVuelo--
    }, fin)
    const a = cola.push('1'); cola.push('2'); cola.push('3')
    await a
    expect(orden).toEqual(['1', '2', '3'])
    expect(maximo).toBe(1)
    expect(fin).toHaveBeenCalledTimes(1)
  })
})

describe('debeRedirigirTecla', () => {
  const base = { enCampo: false, hayDialogo: false }
  it('redirige letras y dígitos fuera de campo y sin diálogo', () => {
    expect(debeRedirigirTecla({ ...base, key: 'a' })).toBe(true)
    expect(debeRedirigirTecla({ ...base, key: '7' })).toBe(true)
  })
  it('nunca toca Enter, Espacio, Tab, Escape ni flechas', () => {
    for (const key of ['Enter', ' ', 'Tab', 'Escape', 'ArrowDown']) expect(debeRedirigirTecla({ ...base, key })).toBe(false)
  })
  it('no actúa con diálogo abierto, dentro de un campo ni con ctrl', () => {
    expect(debeRedirigirTecla({ ...base, key: 'a', hayDialogo: true })).toBe(false)
    expect(debeRedirigirTecla({ ...base, key: 'a', enCampo: true })).toBe(false)
    expect(debeRedirigirTecla({ ...base, key: 'a', ctrlKey: true })).toBe(false)
  })
})
