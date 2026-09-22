/**
 * Pruebas de la aritmética del lote de etiquetas.
 *
 * Lo que se fija aquí es lo que decide cuánto rollo se gasta: el alcance de las
 * acciones en lote, el tope de 500 y qué filas quedan fuera del trabajo.
 */
import { describe, expect, it } from 'vitest'

import type { LabelCandidate } from '../../api/labels'
import {
  MAX_COPIAS,
  MAX_LOTE,
  alcance,
  construirLote,
  copiasIniciales,
  mensajeExceso,
  normalizarCopias,
  ponerN,
  textoResumen,
  usarExistencia,
} from './lote'

function fila(over: Partial<LabelCandidate> & { variant_id: string }): LabelCandidate {
  return {
    product_id: 'p1',
    sku: over.variant_id.toUpperCase(),
    barcode: '2017000000013',
    product_name: 'Chamarra',
    sale_name: 'Chamarra mezclilla',
    brand: 'LV',
    department: 'Caballero',
    gender: 'HOMBRE',
    size: 'M',
    color: 'Negro',
    price: 1800,
    stock: 3,
    copies_default: 3,
    printable: true,
    reason: null,
    ...over,
  }
}

const SIN_SELECCION: ReadonlySet<string> = new Set<string>()

describe('normalizarCopias', () => {
  it('trunca, recorta al rango y tolera basura', () => {
    expect(normalizarCopias('7')).toBe(7)
    expect(normalizarCopias(7.9)).toBe(7)
    expect(normalizarCopias('-4')).toBe(0)
    expect(normalizarCopias(500)).toBe(MAX_COPIAS)
    expect(normalizarCopias('')).toBe(0)
    expect(normalizarCopias('abc')).toBe(0)
  })

  it('deja pasar el 0: es "no imprimas esta fila", no un error', () => {
    expect(normalizarCopias('0')).toBe(0)
  })
})

describe('copiasIniciales', () => {
  it('arranca en la sugerencia del backend', () => {
    const mapa = copiasIniciales([
      fila({ variant_id: 'a', copies_default: 3 }),
      fila({ variant_id: 'b', copies_default: 0 }),
    ])
    expect(mapa).toEqual({ a: 3, b: 0 })
  })
})

describe('alcance', () => {
  const items = [fila({ variant_id: 'a' }), fila({ variant_id: 'b' })]

  it('sin seleccion abarca todo lo visible', () => {
    expect(alcance(items, SIN_SELECCION).map((i) => i.variant_id)).toEqual(['a', 'b'])
  })

  it('con seleccion abarca solo lo marcado', () => {
    expect(alcance(items, new Set(['b'])).map((i) => i.variant_id)).toEqual(['b'])
  })
})

describe('usarExistencia', () => {
  const items = [
    fila({ variant_id: 'a', copies_default: 3 }),
    fila({ variant_id: 'b', copies_default: 5 }),
  ]

  it('sin seleccion aplica a todo lo visible', () => {
    expect(usarExistencia(items, { a: 1, b: 1 }, SIN_SELECCION)).toEqual({ a: 3, b: 5 })
  })

  it('con seleccion no toca lo que no esta marcado', () => {
    expect(usarExistencia(items, { a: 1, b: 1 }, new Set(['b']))).toEqual({ a: 1, b: 5 })
  })

  it('no muta el mapa que recibe', () => {
    const antes = { a: 1, b: 1 }
    usarExistencia(items, antes, SIN_SELECCION)
    expect(antes).toEqual({ a: 1, b: 1 })
  })
})

describe('ponerN', () => {
  const items = [fila({ variant_id: 'a' }), fila({ variant_id: 'b' })]

  it('solo toca lo seleccionado', () => {
    expect(ponerN(items, { a: 1, b: 1 }, new Set(['a']), 4)).toEqual({ a: 4, b: 1 })
  })

  it('sin seleccion no hace nada: poner N a todo no se pide por accidente', () => {
    const antes = { a: 1, b: 1 }
    expect(ponerN(items, antes, SIN_SELECCION, 4)).toBe(antes)
  })

  it('recorta al tope por renglon', () => {
    expect(ponerN(items, { a: 1, b: 1 }, new Set(['a']), 250)).toEqual({ a: MAX_COPIAS, b: 1 })
  })
})

describe('construirLote', () => {
  it('suma las copias de lo imprimible', () => {
    const items = [fila({ variant_id: 'a' }), fila({ variant_id: 'b' })]
    const r = construirLote(items, { a: 2, b: 3 }, SIN_SELECCION)
    expect(r.items).toEqual([
      { variant_id: 'a', copies: 2 },
      { variant_id: 'b', copies: 3 },
    ])
    expect(r.etiquetas).toBe(5)
    expect(r.excede).toBe(false)
  })

  it('saca del trabajo lo no imprimible pero lo reporta con su motivo', () => {
    const items = [
      fila({ variant_id: 'a' }),
      fila({ variant_id: 'b', printable: false, reason: 'Sin código de barras', sku: 'PLAY-BLA-CH' }),
    ]
    const r = construirLote(items, { a: 2, b: 9 }, SIN_SELECCION)
    expect(r.items).toEqual([{ variant_id: 'a', copies: 2 }])
    expect(r.omitidas).toEqual([
      { variant_id: 'b', sku: 'PLAY-BLA-CH', reason: 'Sin código de barras' },
    ])
    expect(r.etiquetas).toBe(2)
  })

  it('inventa un motivo si el backend no lo manda', () => {
    const items = [fila({ variant_id: 'a', printable: false, reason: null })]
    expect(construirLote(items, { a: 1 }, SIN_SELECCION).omitidas[0].reason).toBe('No se puede imprimir')
  })

  it('cuenta aparte las filas que el usuario dejo en 0', () => {
    const items = [fila({ variant_id: 'a' }), fila({ variant_id: 'b' })]
    const r = construirLote(items, { a: 0, b: 2 }, SIN_SELECCION)
    expect(r.items).toEqual([{ variant_id: 'b', copies: 2 }])
    expect(r.sinCopias).toBe(1)
    expect(r.omitidas).toEqual([])
  })

  it('cae a copies_default cuando la fila no esta en el mapa', () => {
    const items = [fila({ variant_id: 'a', copies_default: 4 })]
    expect(construirLote(items, {}, SIN_SELECCION).etiquetas).toBe(4)
  })

  it('respeta la seleccion', () => {
    const items = [fila({ variant_id: 'a' }), fila({ variant_id: 'b' })]
    const r = construirLote(items, { a: 2, b: 3 }, new Set(['b']))
    expect(r.items).toEqual([{ variant_id: 'b', copies: 3 }])
    expect(r.etiquetas).toBe(3)
  })

  it('marca el exceso justo arriba de 500, no en 500', () => {
    const items = Array.from({ length: 10 }, (_, i) => fila({ variant_id: `v${i}` }))
    const cincuenta = Object.fromEntries(items.map((i) => [i.variant_id, 50]))
    const exacto = construirLote(items, cincuenta, SIN_SELECCION)
    expect(exacto.etiquetas).toBe(MAX_LOTE)
    expect(exacto.excede).toBe(false)

    const unaMas = construirLote(items, { ...cincuenta, v0: 51 }, SIN_SELECCION)
    expect(unaMas.etiquetas).toBe(MAX_LOTE + 1)
    expect(unaMas.excede).toBe(true)
  })
})

describe('mensajeExceso', () => {
  it('dice cuanto suma y que hacer', () => {
    expect(mensajeExceso(594)).toBe(
      'El lote suma 594 etiquetas y el máximo es 500. Quita renglones o baja las copias.',
    )
  })
})

describe('textoResumen', () => {
  it('singulariza y solo menciona lo que hay', () => {
    const items = [fila({ variant_id: 'a' })]
    expect(textoResumen(construirLote(items, { a: 1 }, SIN_SELECCION))).toBe('1 etiqueta · 1 renglón')
  })

  it('menciona omitidas y filas en cero', () => {
    const items = [
      fila({ variant_id: 'a' }),
      fila({ variant_id: 'b' }),
      fila({ variant_id: 'c', printable: false, reason: 'Sin código de barras' }),
    ]
    const texto = textoResumen(construirLote(items, { a: 3, b: 0, c: 1 }, SIN_SELECCION))
    expect(texto).toBe('3 etiquetas · 1 renglón · 1 sin código de barras · 1 en 0 copias')
  })
})
