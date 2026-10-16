// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { conAlpha, token } from '../cssToken'

afterEach(() => {
  document.body.innerHTML = ''
  document.documentElement.style.removeProperty('--p-accent')
})

describe('token', () => {
  it('prefiere el valor de .pv2 sobre el de :root', () => {
    document.documentElement.style.setProperty('--p-accent', '#111111')
    document.body.innerHTML = '<div class="pv2" style="--p-accent: #222222"></div>'
    expect(token('--p-accent', '#6366f1')).toBe('#222222')
  })
  it('con valor vacío devuelve el respaldo', () => {
    expect(token('--p-no-existe', '#6366f1')).toBe('#6366f1')
  })
  it('acepta un elemento explícito', () => {
    document.body.innerHTML = '<div id="x" style="--p-accent: #333333"></div>'
    expect(token('--p-accent', '#6366f1', document.getElementById('x'))).toBe('#333333')
  })
  it('sin variable definida devuelve el respaldo (chart.js no entiende var())', () => {
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
