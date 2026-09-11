import { describe, expect, it } from 'vitest'
import {
  COMPARE_OPTIONS, compareLabel, deltaTone, fmtDeltaCell, showDeltaColumns,
} from '../compareFormat'

// Spec 2026-09-09 §5.1: el delta va como columna junto a cada cifra; sin
// referencia se pinta un guion, no un 0%. Bajo 768 px las columnas Δ se
// ocultan y el delta baja debajo de la cifra.
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
    expect(fmtDeltaCell(9)).toEqual({ text: '▲ 9.0%', tone: 'up' })
    expect(fmtDeltaCell(-4.25)).toEqual({ text: '▼ 4.3%', tone: 'down' })
    expect(fmtDeltaCell(0)).toEqual({ text: '=', tone: 'flat' })
    expect(fmtDeltaCell(null)).toEqual({ text: '—', tone: 'flat' })
    expect(fmtDeltaCell(undefined)).toEqual({ text: '—', tone: 'flat' })
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

describe('showDeltaColumns', () => {
  it('se ocultan por debajo de 768 px', () => {
    expect(showDeltaColumns(1366)).toBe(true)
    expect(showDeltaColumns(768)).toBe(true)
    expect(showDeltaColumns(767)).toBe(false)
    expect(showDeltaColumns(375)).toBe(false)
  })
})
