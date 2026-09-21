import { describe, it, expect } from 'vitest'
import { posicionaPopover, ANCHO_POPOVER, MARGEN_POPOVER } from '../popoverPos'

// Disparador típico: el botón de precio/u de una línea del carrito.
const ancla = (top: number, left: number, alto = 40) => ({ top, bottom: top + alto, left })

describe('posicionaPopover — ancho', () => {
  it('usa el ancho deseado cuando cabe (escritorio)', () => {
    const p = posicionaPopover(ancla(100, 400), 280, 1440, 900)
    expect(p.width).toBe(ANCHO_POPOVER)
  })

  it('se recorta al viewport menos el margen en una pantalla angosta (M2)', () => {
    // Con 300 px fijos el popover tocaba los bordes (o los pasaba) en las
    // pantallas más angostas; ahora nunca excede vw − 2×margen.
    const p = posicionaPopover(ancla(100, 10), 280, 300, 640)
    expect(p.width).toBe(300 - 2 * MARGEN_POPOVER)
    expect(p.left).toBe(MARGEN_POPOVER)
    // Y no se sale por la derecha.
    expect(p.left + p.width).toBeLessThanOrEqual(300 - MARGEN_POPOVER)
  })

  it('en un Android de 360 px deja el ancho deseado y lo mete en pantalla', () => {
    const p = posicionaPopover(ancla(100, 80), 280, 360, 640)
    expect(p.width).toBe(ANCHO_POPOVER)
    expect(p.left).toBe(360 - ANCHO_POPOVER - MARGEN_POPOVER)
  })

  it('nunca devuelve un ancho negativo aunque el viewport sea absurdo', () => {
    expect(posicionaPopover(ancla(0, 0), 280, 10, 100).width).toBe(0)
  })
})

describe('posicionaPopover — colocación vertical', () => {
  it('cae debajo del disparador cuando hay espacio', () => {
    const p = posicionaPopover(ancla(100, 400), 280, 1440, 900)
    expect(p.placement).toBe('below')
    expect(p.top).toBe(144) // bottom (140) + 4 de separación
  })

  it('sube encima cuando abajo no cabe y arriba sí', () => {
    // Línea al fondo de la pantalla: 900 − 860 − 8 = 32 px abajo, 820 arriba.
    const p = posicionaPopover(ancla(820, 400), 280, 1440, 900)
    expect(p.placement).toBe('above')
    expect(p.top).toBe(820 - 280 - 4)
  })

  it('cuando no cabe ni arriba ni abajo se queda abajo', () => {
    const p = posicionaPopover(ancla(150, 20), 280, 390, 400)
    expect(p.placement).toBe('below')
  })

  it('nunca coloca el borde superior fuera de la pantalla', () => {
    const p = posicionaPopover(ancla(60, 20), 280, 390, 300)
    expect(p.top).toBeGreaterThanOrEqual(0)
  })
})

describe('posicionaPopover — colocación horizontal', () => {
  it('se alinea con el disparador cuando cabe', () => {
    expect(posicionaPopover(ancla(100, 400), 280, 1440, 900).left).toBe(400)
  })

  it('se recoge contra el borde derecho', () => {
    const p = posicionaPopover(ancla(100, 1300), 280, 1440, 900)
    expect(p.left).toBe(1440 - ANCHO_POPOVER - MARGEN_POPOVER)
  })

  it('respeta el margen izquierdo', () => {
    expect(posicionaPopover(ancla(100, 0), 280, 1440, 900).left).toBe(MARGEN_POPOVER)
  })
})
