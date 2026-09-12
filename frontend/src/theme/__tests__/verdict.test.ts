import { describe, it, expect } from 'vitest'
import { closeVerdict } from '../verdict'

describe('closeVerdict — color y texto de la diferencia al cerrar caja (A6)', () => {
  it('cero o hasta ±$0.99 cuadra (verde)', () => {
    expect(closeVerdict(0).kind).toBe('ok')
    expect(closeVerdict(0.5).kind).toBe('ok')
    expect(closeVerdict(-0.99).kind).toBe('ok')
    expect(closeVerdict(0).label).toBe('Caja cuadrada')
  })
  it('positivo sobra (ámbar)', () => {
    const v = closeVerdict(120)
    expect(v.kind).toBe('over')
    expect(v.label).toBe('Sobrante')
  })
  it('negativo falta (rojo)', () => {
    const v = closeVerdict(-221)
    expect(v.kind).toBe('short')
    expect(v.label).toBe('Faltante')
  })
  it('NaN se trata como cuadrada para no asustar con basura', () => {
    expect(closeVerdict(NaN).kind).toBe('ok')
  })
  it('cada veredicto lleva una clase de color distinta', () => {
    const set = new Set([closeVerdict(0).className, closeVerdict(1).className, closeVerdict(-1).className])
    expect(set.size).toBe(3)
  })
  it('el color sale de los tokens de Atlas ONE, no de una paleta fija de Tailwind', () => {
    for (const d of [0, 1, -1]) {
      const cls = closeVerdict(d).className
      expect(cls).toMatch(/^verdict verdict-(ok|over|short)$/)
      expect(cls).not.toMatch(/emerald|amber|rose|slate/)
    }
  })
})
