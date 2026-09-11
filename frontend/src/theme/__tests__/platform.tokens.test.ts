import { describe, it, expect } from 'vitest'

// Spec 2026-09-09 §3.1 (piel C): la piel del nivel SUPERADMIN entra por alias
// de tokens. Cada --p-* que define index.css tiene que estar redefinido dentro
// de `.pv2` como var(--dax-*), para que el ThemeContext global (clase .dark en
// <html>) y el acento por vertical manden también en /platform.
// A diferencia del origen (Rmazh) aquí NO existe la bandera `atlas_ui_legacy`:
// los valores de --dax-* no cambian, así que no hay nada a lo que volver.
// El CSS entra como texto (`?raw`, Vite): el proyecto no tiene @types/node,
// así que las pruebas leen archivos por el bundler y no por `node:fs`.
import css from '../../styles/platform-v2.css?raw'
import root from '../../index.css?raw'

const rootTokens = [...new Set([...root.matchAll(/^\s*(--p-[a-z0-9-]+)\s*:/gm)].map((m) => m[1]))]

function block(selector: string): string {
  const start = css.indexOf(selector + ' {')
  expect(start, `falta el bloque "${selector} {"`).toBeGreaterThan(-1)
  const end = css.indexOf('}', start)
  return css.slice(start, end)
}

/** Tokens --dax-* declarados en el bloque claro (:root) o en el oscuro (.dark). */
function extractDaxTokens(theme: 'light' | 'dark'): Record<string, string> {
  const blockContent = theme === 'light' ? root.split('.dark {')[0] : root.split('.dark {')[1]?.split('}')[0] || ''
  const tokens: Record<string, string> = {}
  for (const match of blockContent.matchAll(/^\s*(--dax-[a-z0-9-]+)\s*:\s*([^;]+);/gm)) {
    tokens[match[1]] = match[2].trim()
  }
  return tokens
}

/** Valor final de cada --p-* del alias, por tema, ya resuelto a su --dax-*. */
function resolveAliases(): Record<'light' | 'dark', Record<string, string>> {
  const lightDax = extractDaxTokens('light')
  const darkDax = extractDaxTokens('dark')
  const pv2Block = block('.pv2')
  const resolved: Record<'light' | 'dark', Record<string, string>> = { light: {}, dark: {} }
  for (const match of pv2Block.matchAll(/^\s*(--p-[a-z0-9-]+)\s*:\s*var\((--dax-[a-z0-9-]+)\)/gm)) {
    const [, pToken, daxToken] = match
    resolved.light[pToken] = lightDax[daxToken] ?? '?'
    // El oscuro solo redefine parte del set; lo que no redefine lo hereda del claro.
    resolved.dark[pToken] = darkDax[daxToken] ?? lightDax[daxToken] ?? '?'
  }
  return resolved
}

describe('alias --p-* → --dax-* (spec §3.1)', () => {
  it('index.css define al menos los tokens base', () => {
    expect(rootTokens).toEqual(expect.arrayContaining(['--p-bg', '--p-surface', '--p-accent', '--p-danger']))
  })

  it('cada token --p-* de index.css está aliasado a var(--dax-*) dentro de .pv2', () => {
    const alias = block('.pv2')
    const missing = rootTokens.filter((t) => !new RegExp(`${t}\\s*:\\s*var\\(--dax-`).test(alias))
    expect(missing).toEqual([])
  })

  it('cada --dax-* que usa el alias existe en index.css, en claro', () => {
    const lightDax = extractDaxTokens('light')
    const used = [...new Set([...block('.pv2').matchAll(/var\((--dax-[a-z0-9-]+)\)/g)].map((m) => m[1]))]
    expect(used.filter((t) => !(t in lightDax))).toEqual([])
  })

  it('no quedan colores fijos en platform-v2.css salvo #fff', () => {
    const hits = [...css.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map((m) => m[0].toLowerCase())
      .filter((h) => h !== '#fff' && h !== '#ffffff')
    expect(hits).toEqual([])
  })

  it('no quedan rgba( ni hsl( literales en platform-v2.css', () => {
    const hits = [...css.matchAll(/\b(rgba|hsl)\(/g)].map((m) => m[0])
    expect(hits).toEqual([])
  })

  it('--p-border es distinto de --p-surface-2 en ambos temas', () => {
    const resolved = resolveAliases()
    expect(resolved.light['--p-border']).not.toBe(resolved.light['--p-surface-2'])
    expect(resolved.dark['--p-border']).not.toBe(resolved.dark['--p-surface-2'])
  })

  it('--p-border es distinto de --p-surface en ambos temas', () => {
    const resolved = resolveAliases()
    expect(resolved.light['--p-border']).not.toBe(resolved.light['--p-surface'])
    expect(resolved.dark['--p-border']).not.toBe(resolved.dark['--p-surface'])
  })

  it('--p-surface-2 es distinto de --p-surface en ambos temas (hover de fila visible)', () => {
    const resolved = resolveAliases()
    expect(resolved.light['--p-surface-2']).not.toBe(resolved.light['--p-surface'])
    expect(resolved.dark['--p-surface-2']).not.toBe(resolved.dark['--p-surface'])
  })

  it('los cuatro tokens nuevos existen en claro y en oscuro', () => {
    const nuevos = ['--dax-accent-soft', '--dax-success', '--dax-warning', '--dax-danger']
    const lightDax = extractDaxTokens('light')
    const darkDax = extractDaxTokens('dark')
    expect(nuevos.filter((t) => !(t in lightDax))).toEqual([])
    expect(nuevos.filter((t) => !(t in darkDax))).toEqual([])
  })
})
