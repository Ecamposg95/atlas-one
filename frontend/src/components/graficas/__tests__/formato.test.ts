import { describe, it, expect } from 'vitest'
import { dineroCorto, etiquetaHora, recortarHoras } from '../formato'

describe('dineroCorto', () => {
  it('abrevia miles y millones con un decimal', () => {
    expect(dineroCorto(950)).toBe('$950')
    expect(dineroCorto(1234)).toBe('$1.2k')
    expect(dineroCorto(12500)).toBe('$12.5k')
    expect(dineroCorto(3_400_000)).toBe('$3.4M')
    expect(dineroCorto(0)).toBe('$0')
  })
  it('redondea en los umbrales: 999.5 es $1.0k, 999 950 es $1.0M y -0.4 es $0 sin signo', () => {
    expect(dineroCorto(999.4)).toBe('$999')
    expect(dineroCorto(999.5)).toBe('$1.0k')
    expect(dineroCorto(999_949)).toBe('$999.9k')
    expect(dineroCorto(999_950)).toBe('$1.0M')
    expect(dineroCorto(-0.4)).toBe('$0')
    expect(dineroCorto(-999.5)).toBe('-$1.0k')
  })
  it('negativos con signo delante (un día con más devoluciones que ventas)', () => {
    expect(dineroCorto(-1234)).toBe('-$1.2k')
    expect(dineroCorto(-40)).toBe('-$40')
  })
})

describe('recortarHoras (spec §2.1: min(9, primera con venta) .. max(21, última con venta))', () => {
  const horas = (con: Record<number, number>) => Array.from({ length: 24 }, (_, h) => ({ hora: h, neta: con[h] ?? 0 }))
  it('sin ventas: de 9 a 21', () => {
    expect(recortarHoras(horas({}))).toEqual({ desde: 9, hasta: 21 })
  })
  it('una venta dentro de la ventana no la mueve', () => {
    expect(recortarHoras(horas({ 12: 100 }))).toEqual({ desde: 9, hasta: 21 })
  })
  it('ventas temprano o tarde la abren', () => {
    expect(recortarHoras(horas({ 7: 100 }))).toEqual({ desde: 7, hasta: 21 })
    expect(recortarHoras(horas({ 23: 100 }))).toEqual({ desde: 9, hasta: 23 })
  })
  it('una devolución (neta negativa) también cuenta como movimiento', () => {
    expect(recortarHoras(horas({ 6: -40 }))).toEqual({ desde: 6, hasta: 21 })
  })
})

describe('recortarHoras con tickets', () => {
  it('una hora con tickets abre la ventana aunque su neta sea 0 (venta y devolución iguales)', () => {
    const horas = Array.from({ length: 24 }, (_, h) => ({ hora: h, neta: 0, tickets: h === 7 ? 1 : 0 }))
    expect(recortarHoras(horas)).toEqual({ desde: 7, hasta: 21 })
  })
})

describe('etiquetaHora', () => {
  it('pinta "9:00"', () => {
    expect(etiquetaHora(9)).toBe('9:00')
    expect(etiquetaHora(0)).toBe('0:00')
  })
})
