import { describe, it, expect } from 'vitest'
import { porcentaje } from './porcentaje'

describe('porcentaje', () => {
  it('parte sobre total, a un decimal', () => {
    expect(porcentaje(5000, 10200)).toBe(49)
    expect(porcentaje(5200, 10200)).toBe(51)
    expect(porcentaje(1, 3)).toBe(33.3)
  })
  it('sin total no divide: 0', () => {
    expect(porcentaje(10, 0)).toBe(0)
    expect(porcentaje(0, 0)).toBe(0)
  })
  it('el todo es 100', () => {
    expect(porcentaje(10200, 10200)).toBe(100)
  })
})
