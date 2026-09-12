import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import { isNativeDetectorAvailable, FORMATS, normalizeCode, normalizeTyped } from '../barcodeReader'

// Chrome en Android trae `BarcodeDetector` en el navegador: decodifica sin
// librería y sin sumar peso al bundle. Safari en iPhone no lo trae, y ahí hay
// que cargar una librería por `import()` dinámico. La decisión se toma en
// runtime, así que tiene que ser una función consultable y testeable — si se
// equivoca, o el Android paga un peso que no debía, o el iPhone no escanea.

const g = globalThis as unknown as Record<string, unknown>

describe('isNativeDetectorAvailable', () => {
  let original: unknown

  beforeEach(() => { original = g.BarcodeDetector })
  afterEach(() => {
    if (original === undefined) delete g.BarcodeDetector
    else g.BarcodeDetector = original
  })

  it('es true cuando el navegador expone BarcodeDetector', () => {
    g.BarcodeDetector = class {}
    expect(isNativeDetectorAvailable()).toBe(true)
  })

  it('es false cuando no existe (Safari / iPhone)', () => {
    delete g.BarcodeDetector
    expect(isNativeDetectorAvailable()).toBe(false)
  })
})

describe('FORMATS', () => {
  it('cubre los formatos que trae el catálogo', () => {
    // 1,564 SKUs son EAN-13, 121 UPC-A y 8 EAN-8. Sin EAN-8 en la lista, esos
    // productos simplemente no escanean.
    expect(FORMATS).toContain('ean_13')
    expect(FORMATS).toContain('upc_a')
    expect(FORMATS).toContain('ean_8')
  })
})

describe('normalizeCode', () => {
  it('quita espacios de los extremos', () => {
    expect(normalizeCode('  750123456789 ')).toBe('750123456789')
  })

  it('quita el guion que algunos lectores insertan', () => {
    expect(normalizeCode('7501-23456789')).toBe('750123456789')
  })

  it('devuelve cadena vacía para basura', () => {
    expect(normalizeCode('   ')).toBe('')
    expect(normalizeCode(null)).toBe('')
    expect(normalizeCode(undefined)).toBe('')
  })

  it('NO recorta ceros a la izquierda', () => {
    // Un EAN-13 puede empezar con 0 y es significativo; recortarlo convierte el
    // código en otro producto.
    expect(normalizeCode('0750123456789')).toBe('0750123456789')
  })
})

// El scanner tiene DOS entradas y no pueden limpiarse igual.
//
// La cámara devuelve el código con ruido: algunos lectores insertan guiones o
// espacios. Ahí `normalizeCode` es correcto.
//
// El campo de texto dice "O teclea el código / SKU", y 2,259 SKUs del catálogo
// llevan letras y guiones (`m-1151`, `SKU-CORTO`). Pasarlos por la misma
// función los convierte en `m1151` y la búsqueda EXACTA del backend ya no
// empata — y encima ofrece pegarle ese texto mutilado como código de barras.
describe('normalizeTyped', () => {
  it('CONSERVA el guion de un SKU', () => {
    expect(normalizeTyped('m-1151')).toBe('m-1151')
    expect(normalizeTyped('SKU-CORTO')).toBe('SKU-CORTO')
  })

  it('conserva espacios internos de un código interno', () => {
    expect(normalizeTyped('LAPIZ DUO JUMBO')).toBe('LAPIZ DUO JUMBO')
  })

  it('recorta los extremos', () => {
    expect(normalizeTyped('  750123456789  ')).toBe('750123456789')
  })

  it('vacío sigue siendo vacío', () => {
    expect(normalizeTyped('   ')).toBe('')
    expect(normalizeTyped(null)).toBe('')
  })
})
