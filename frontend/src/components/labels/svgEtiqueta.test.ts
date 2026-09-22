/**
 * Pruebas de la geometría de la vista previa.
 *
 * La etiqueta que se dibuja en pantalla sale de los MISMOS elementos que el
 * ZPL. Si `bits` se traduce mal a rectángulos, la pantalla miente sobre lo que
 * va a salir del rollo — y eso es justo lo que la vista previa existe para
 * evitar.
 */
import { describe, expect, it } from 'vitest'

import {
  anchoDeBits,
  anclaTexto,
  barrasDeBits,
  centroInterpretacion,
  lineaBase,
} from './svgEtiqueta'

describe('barrasDeBits', () => {
  it('ignora los espacios y solo dibuja las barras', () => {
    expect(barrasDeBits('1010', 0, 76, 48, 1)).toEqual([
      { x: 0, y: 76, width: 1, height: 48 },
      { x: 2, y: 76, width: 1, height: 48 },
    ])
  })

  it('funde barras contiguas en un solo rectangulo', () => {
    expect(barrasDeBits('1110', 0, 0, 10, 1)).toEqual([{ x: 0, y: 0, width: 3, height: 10 }])
  })

  it('escala cada modulo por module_width', () => {
    expect(barrasDeBits('0110', 100, 76, 48, 3)).toEqual([
      { x: 103, y: 76, width: 6, height: 48 },
    ])
  })

  it('cierra la racha que llega hasta el final de la cadena', () => {
    expect(barrasDeBits('0011', 0, 0, 10, 2)).toEqual([{ x: 4, y: 0, width: 4, height: 10 }])
  })

  it('devuelve vacio cuando no hay barras', () => {
    expect(barrasDeBits('', 0, 0, 10, 2)).toEqual([])
    expect(barrasDeBits('0000', 0, 0, 10, 2)).toEqual([])
  })

  it('trata como espacio cualquier caracter que no sea 1', () => {
    expect(barrasDeBits('1x1', 0, 0, 10, 1)).toEqual([
      { x: 0, y: 0, width: 1, height: 10 },
      { x: 2, y: 0, width: 1, height: 10 },
    ])
  })

  it('nunca dibuja un modulo de ancho cero', () => {
    expect(barrasDeBits('1', 0, 0, 10, 0)[0].width).toBe(1)
  })

  it('conserva el ancho total de un EAN-13 (95 modulos)', () => {
    // Patrón real: guarda + 6 dígitos + separador central + 6 + guarda.
    const bits = '101' + '0001101'.repeat(6) + '01010' + '1110010'.repeat(6) + '101'
    expect(bits.length).toBe(95)
    const rects = barrasDeBits(bits, 109, 76, 48, 2)
    const derecha = Math.max(...rects.map((r) => r.x + r.width))
    expect(derecha - 109).toBeLessThanOrEqual(anchoDeBits(bits, 2))
    expect(rects.every((r) => r.height === 48 && r.y === 76)).toBe(true)
  })
})

describe('anchoDeBits', () => {
  it('multiplica modulos por dots', () => {
    expect(anchoDeBits('10101', 2)).toBe(10)
    expect(anchoDeBits('10101', 0)).toBe(5)
  })
})

describe('lineaBase', () => {
  it('baja la y del tope de la celda a la base de la letra', () => {
    expect(lineaBase(8, 22)).toBeCloseTo(25.6)
  })
})

describe('anclaTexto', () => {
  it('alinea a la izquierda por omision', () => {
    expect(anclaTexto({ x: 12, width: null, align: 'L' })).toEqual({ x: 12, anchor: 'start' })
  })

  it('ancla el precio al borde derecho de su caja ^FB', () => {
    expect(anclaTexto({ x: 246, width: 150, align: 'R' })).toEqual({ x: 396, anchor: 'end' })
  })

  it('sin ancho de caja no puede alinear a la derecha', () => {
    expect(anclaTexto({ x: 246, width: null, align: 'R' })).toEqual({ x: 246, anchor: 'start' })
  })
})

describe('centroInterpretacion', () => {
  it('centra la linea legible bajo las barras', () => {
    expect(centroInterpretacion({ x: 100, bits: '1010', module_width: 2 })).toBe(104)
  })
})
