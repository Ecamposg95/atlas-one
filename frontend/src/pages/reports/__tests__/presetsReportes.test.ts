import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  PRESETS, diasDelRango, diasHastaHoy, etiquetaRango, etiquetasTendencia, fechasDelRango, presetActivo, rangoPreset,
} from '../presetsReportes'

// 23 de octubre de 2026 (viernes), mediodía local.
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date(2026, 9, 23, 12)) })
afterEach(() => vi.useRealTimers())

describe('rangoPreset (mismos tramos que metricas_ventas.periodo_preset)', () => {
  it('hoy, ayer, 7 días, 30 días y este mes', () => {
    expect(rangoPreset('hoy')).toEqual({ inicio: '2026-10-23', fin: '2026-10-23' })
    expect(rangoPreset('ayer')).toEqual({ inicio: '2026-10-22', fin: '2026-10-22' })
    expect(rangoPreset('7d')).toEqual({ inicio: '2026-10-17', fin: '2026-10-23' })
    expect(rangoPreset('30d')).toEqual({ inicio: '2026-09-24', fin: '2026-10-23' })
    expect(rangoPreset('mes')).toEqual({ inicio: '2026-10-01', fin: '2026-10-23' })
  })
  it('la barra va en el orden de la spec', () => {
    expect(PRESETS.map((p) => p.etiqueta)).toEqual(['Hoy', 'Ayer', '7 días', '30 días', 'Este mes'])
  })
})

describe('presetActivo', () => {
  it('reconoce el preset del rango y null para uno a mano', () => {
    expect(presetActivo(rangoPreset('mes'))).toBe('mes')
    expect(presetActivo({ inicio: '2026-10-17', fin: '2026-10-23' })).toBe('7d')
    expect(presetActivo({ inicio: '2026-10-10', fin: '2026-10-23' })).toBeNull()
  })
})

describe('fechas del rango', () => {
  it('fechasDelRango enumera cada día y diasDelRango las cuenta', () => {
    const f = fechasDelRango(rangoPreset('7d'))
    expect(f).toHaveLength(7)
    expect(f[0]).toBe('2026-10-17')
    expect(f[6]).toBe('2026-10-23')
    expect(diasDelRango(rangoPreset('hoy'))).toBe(1)
    expect(diasDelRango(rangoPreset('30d'))).toBe(30)
  })
  it('etiquetaRango: un día solo o "desde – hasta"', () => {
    expect(etiquetaRango(rangoPreset('hoy'))).toMatch(/23.*oct/)
    expect(etiquetaRango(rangoPreset('7d'))).toMatch(/17.*oct.* – .*23.*oct/)
  })
  it('etiquetasTendencia usa las fechas del rango en español cuando cuadran y las del servidor si no', () => {
    const e = etiquetasTendencia(rangoPreset('7d'), 7, ['Sat 17', 'Sun 18', 'Mon 19', 'Tue 20', 'Wed 21', 'Thu 22', 'Fri 23'])
    expect(e).toHaveLength(7)
    expect(e[0]).toMatch(/sáb.*17/)
    expect(e[6]).toMatch(/vie.*23/)
    expect(etiquetasTendencia(rangoPreset('7d'), 5, ['a', 'b', 'c', 'd', 'e'])).toEqual(['a', 'b', 'c', 'd', 'e'])
  })
})

describe('diasHastaHoy (promedio por hora de rangos a mano)', () => {
  it('recorta el fin a hoy y nunca baja de 1', () => {
    expect(diasHastaHoy({ inicio: '2026-10-17', fin: '2026-10-30' })).toBe(7)   // 17..23
    expect(diasHastaHoy({ inicio: '2026-10-17', fin: '2026-10-23' })).toBe(7)
    expect(diasHastaHoy({ inicio: '2026-10-10', fin: '2026-10-12' })).toBe(3)   // todo pasado: igual que diasDelRango
    expect(diasHastaHoy({ inicio: '2026-10-28', fin: '2026-10-30' })).toBe(1)   // todo futuro
  })
})

describe('presets en frontera de mes (día 1)', () => {
  it('el 1 de noviembre: mes es un solo día y ayer es el 31 de octubre', () => {
    vi.setSystemTime(new Date(2026, 10, 1, 12))
    expect(rangoPreset('mes')).toEqual({ inicio: '2026-11-01', fin: '2026-11-01' })
    expect(diasDelRango(rangoPreset('mes'))).toBe(1)
    expect(rangoPreset('ayer')).toEqual({ inicio: '2026-10-31', fin: '2026-10-31' })
    expect(rangoPreset('7d')).toEqual({ inicio: '2026-10-26', fin: '2026-11-01' })
  })
})
