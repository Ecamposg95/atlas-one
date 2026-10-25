import { describe, it, expect } from 'vitest'
import { porcentajeVariacion, variacion } from '../variacion'

describe('porcentajeVariacion', () => {
  it('porcentaje entero contra el anterior', () => {
    expect(porcentajeVariacion(112, 100)).toBe(12)
    expect(porcentajeVariacion(88, 100)).toBe(-12)
    expect(porcentajeVariacion(0, 100)).toBe(-100)
    expect(porcentajeVariacion(1234.5, 800)).toBe(54)
  })
  it('redondea: 100.4 contra 100 es igual', () => {
    expect(porcentajeVariacion(100.4, 100)).toBe(0)
    expect(porcentajeVariacion(100, 100)).toBe(0)
  })
  it('sin referencia cuando el anterior es cero o negativo', () => {
    expect(porcentajeVariacion(50, 0)).toBeNull()
    expect(porcentajeVariacion(50, -10)).toBeNull()
  })
  it('una cifra que no es finita no tiene variación', () => {
    expect(porcentajeVariacion(NaN, 100)).toBeNull()
    expect(porcentajeVariacion(Infinity, 100)).toBeNull()
  })
  it('cero contra cero es igual, no "sin referencia"', () => {
    expect(porcentajeVariacion(0, 0)).toBe(0)
  })
})

describe('variacion', () => {
  it('arma el objeto con texto e inversión', () => {
    expect(variacion(120, 100, 'vs ayer')).toEqual({ pct: 20, texto: 'vs ayer', invertida: false })
    expect(variacion(400, 100, 'vs periodo anterior', true)).toEqual({ pct: 300, texto: 'vs periodo anterior', invertida: true })
  })
})
