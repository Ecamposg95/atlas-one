import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * Tema "full black" (2026-11-14): la barra lateral es lo más oscuro (#000000),
 * el cuerpo un poco menos, todo neutro, sin tinte índigo.
 */
const css = readFileSync(resolve(__dirname, '..', 'index.css'), 'utf8')

function bloque(selector: string): string {
  const i = css.indexOf(`\n  ${selector} {`)
  expect(i, `no encontré ${selector}`).toBeGreaterThan(-1)
  return css.slice(i, css.indexOf('\n  }', i))
}
const valor = (b: string, token: string) =>
  new RegExp(`${token}:\\s*([^;]+);`).exec(b)?.[1].trim()

describe('tema full black', () => {
  const root = bloque(':root')
  const dark = bloque('.dark')

  it('la barra lateral es negro puro en claro y oscuro', () => {
    expect(valor(root, '--sb-bg')).toBe('#000000')
    expect(valor(dark, '--sb-bg')).toBe('#000000')
  })

  it('el modo oscuro usa grises neutros, con el cuerpo más claro que la barra', () => {
    expect(valor(dark, '--dax-bg')).toBe('#0a0a0a')
    expect(valor(dark, '--dax-surface')).toBe('#111111')
    expect(valor(dark, '--dax-card-solid')).toBe('#161616')
    expect(valor(dark, '--dax-on-accent')).toBe('#000000')
  })

  it('no queda ningún hex índigo de la paleta vieja en .dark', () => {
    for (const hex of ['#0b0b22', '#10102a', '#14142e', '#0e0e28'])
      expect(dark.toLowerCase()).not.toContain(hex)
  })
})
