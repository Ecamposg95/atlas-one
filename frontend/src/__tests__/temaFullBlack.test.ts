import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * Tema oscuro Atlas Horizon (2026-11-18; antes "full black", 2026-11-14): la
 * barra lateral es lo más oscuro (#000000), el cuerpo negro cálido, sin tinte
 * índigo, con el ámbar de la marca como único acento.
 */
const css = readFileSync(resolve(__dirname, '..', 'index.css'), 'utf8')

function bloque(selector: string): string {
  const i = css.indexOf(`\n  ${selector} {`)
  expect(i, `no encontré ${selector}`).toBeGreaterThan(-1)
  return css.slice(i, css.indexOf('\n  }', i))
}
const valor = (b: string, token: string) =>
  new RegExp(`${token}:\\s*([^;]+);`).exec(b)?.[1].trim()

describe('tema oscuro Horizon', () => {
  const root = bloque(':root')
  const dark = bloque('.dark')

  it('la barra lateral es negro puro en claro y oscuro', () => {
    expect(valor(root, '--sb-bg')).toBe('#000000')
    expect(valor(dark, '--sb-bg')).toBe('#000000')
  })

  it('el modo oscuro usa el negro cálido de Horizon, con el cuerpo más claro que la barra', () => {
    expect(valor(dark, '--dax-bg')).toBe('#050505')
    expect(valor(dark, '--dax-surface')).toBe('#0B0A09')
    expect(valor(dark, '--dax-card-solid')).toBe('#12100F')
    expect(valor(dark, '--dax-on-accent')).toBe('#050505')
  })

  it('el acento es el ámbar en oscuro y el naranja quemado en claro', () => {
    expect(valor(dark, '--dax-accent')).toBe('#FF6A1F')
    expect(valor(root, '--dax-accent')).toBe('#C2410C')
  })

  it('no queda ningún hex índigo de la paleta vieja en .dark', () => {
    for (const hex of ['#0b0b22', '#10102a', '#14142e', '#0e0e28'])
      expect(dark.toLowerCase()).not.toContain(hex)
  })
})

describe('capa de layout sin tinte índigo', () => {
  for (const f of ['Layout.tsx', 'Sidebar.tsx', 'MobileLayout.tsx']) {
    it(`${f} no pinta índigo`, () => {
      const src = readFileSync(resolve(__dirname, '..', 'components/layout', f), 'utf8').toLowerCase()
      expect(src).not.toMatch(/11,\s*11,\s*34|237,\s*237,\s*248|#ededf8/)
      for (const hex of ['#0b0b22', '#10102a', '#14142e', '#0e0e28', '#101022']) expect(src).not.toContain(hex)
    })
  }
})

