// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
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
    expect(conAlpha('#fff', 0.5)).toBe('#fff')
    expect(conAlpha('color-mix(in srgb, red 50%, white)', 0.5)).toBe('color-mix(in srgb, red 50%, white)')
  })
  it('acepta rgb(...) y rgba(...)', () => {
    expect(conAlpha('rgb(1, 2, 3)', 0.5)).toBe('rgba(1, 2, 3, 0.5)')
    expect(conAlpha('rgba(1, 2, 3, 0.9)', 0.5)).toBe('rgba(1, 2, 3, 0.5)')
  })
})

describe('token con color-mix (tema oscuro)', () => {
  it('resuelve el valor con una sonda y devuelve rgb(...)', () => {
    document.documentElement.style.setProperty('--p-accent', 'color-mix(in srgb, #6366f1 62%, #ffffff)')
    const real = window.getComputedStyle.bind(window)
    const espia = vi.spyOn(window, 'getComputedStyle').mockImplementation((el: Element, pseudo?: string | null) => {
      if (el.tagName === 'SPAN') return { color: 'rgb(150, 152, 245)' } as CSSStyleDeclaration
      return real(el, pseudo)
    })
    try {
      expect(token('--p-accent', '#6366f1')).toBe('rgb(150, 152, 245)')
      expect(document.querySelector('span')).toBeNull() // la sonda se retira
    } finally {
      espia.mockRestore()
    }
  })
})
