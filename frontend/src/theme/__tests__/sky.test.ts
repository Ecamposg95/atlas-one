import { describe, it, expect } from 'vitest'
import { skyPeriod, easeOutCubic } from '../sky'

const at = (h: number, m = 0) => new Date(2026, 8, 8, h, m)

describe('skyPeriod — el cielo del saludo según la hora local', () => {
  it('06:00 a 16:59 es día', () => {
    expect(skyPeriod(at(6))).toBe('day')
    expect(skyPeriod(at(12, 30))).toBe('day')
    expect(skyPeriod(at(16, 59))).toBe('day')
  })
  it('17:00 a 19:29 es atardecer', () => {
    expect(skyPeriod(at(17))).toBe('sunset')
    expect(skyPeriod(at(19, 29))).toBe('sunset')
  })
  it('19:30 a 05:59 es noche', () => {
    expect(skyPeriod(at(19, 30))).toBe('night')
    expect(skyPeriod(at(23))).toBe('night')
    expect(skyPeriod(at(0))).toBe('night')
    expect(skyPeriod(at(5, 59))).toBe('night')
  })
})

describe('easeOutCubic — curva del count-up', () => {
  it('arranca en 0 y termina en 1', () => {
    expect(easeOutCubic(0)).toBe(0)
    expect(easeOutCubic(1)).toBe(1)
  })
  it('es monótona y frena al final (más avance en la primera mitad)', () => {
    expect(easeOutCubic(0.5)).toBeGreaterThan(0.5)
    expect(easeOutCubic(0.25)).toBeLessThan(easeOutCubic(0.5))
  })
  it('acota fuera de rango', () => {
    expect(easeOutCubic(-1)).toBe(0)
    expect(easeOutCubic(2)).toBe(1)
  })
})
