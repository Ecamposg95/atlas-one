import { describe, it, expect } from 'vitest'
import { conAlpha, token } from '../cssToken'

describe('token', () => {
  it('fuera del navegador devuelve el respaldo (chart.js no entiende var())', () => {
    expect(token('--p-accent', '#6366f1')).toBe('#6366f1')
  })
})

describe('conAlpha', () => {
  it('convierte #rrggbb a rgba', () => {
    expect(conAlpha('#6366f1', 0.2)).toBe('rgba(99, 102, 241, 0.2)')
  })
  it('deja pasar lo que no es hex de 6', () => {
    expect(conAlpha('rgb(1, 2, 3)', 0.5)).toBe('rgb(1, 2, 3)')
    expect(conAlpha('#fff', 0.5)).toBe('#fff')
  })
})
