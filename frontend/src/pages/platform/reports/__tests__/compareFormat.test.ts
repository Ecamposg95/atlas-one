import { describe, expect, it } from 'vitest'
import { COMPARE_OPTIONS, compareLabel, deltaTone, fmtDeltaCell } from '../compareFormat'

// Spec 2026-09-09 §5.1: el delta va como columna junto a cada cifra; sin
// referencia se pinta un guion, no un 0%. Ocultar la columna bajo 768 px es
// cosa de CSS (`.pv2-delta-col`), no de JS.
describe('compareLabel', () => {
  it('nombra los tres modos en español', () => {
    expect(compareLabel('none')).toBe('Sin comparar')
    expect(compareLabel('prev')).toBe('vs periodo anterior')
    expect(compareLabel('yoy')).toBe('vs año pasado')
  })

  it('COMPARE_OPTIONS trae los tres en orden', () => {
    expect(COMPARE_OPTIONS.map((o) => o.key)).toEqual(['none', 'prev', 'yoy'])
  })
})

describe('fmtDeltaCell', () => {
  it('positivo, negativo, cero y sin referencia', () => {
    expect(fmtDeltaCell(9)).toBe('▲ 9.0%')
    expect(fmtDeltaCell(-4.25)).toBe('▼ 4.3%')
    expect(fmtDeltaCell(0)).toBe('=')
    expect(fmtDeltaCell(null)).toBe('—')
    expect(fmtDeltaCell(undefined)).toBe('—')
  })
})

describe('deltaTone', () => {
  it('por default más es mejor', () => {
    expect(deltaTone(5)).toBe('up')
    expect(deltaTone(-5)).toBe('down')
  })

  it('con lowerIsBetter el tono se invierte (faltantes, devoluciones)', () => {
    expect(deltaTone(5, true)).toBe('down')
    expect(deltaTone(-5, true)).toBe('up')
    expect(deltaTone(0, true)).toBe('flat')
    expect(deltaTone(null, true)).toBe('flat')
  })
})
