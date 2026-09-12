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

  it('cada --dax-* que usa platform-v2.css existe en index.css, en claro', () => {
    const lightDax = extractDaxTokens('light')
    const used = [...new Set([...css.matchAll(/var\((--dax-[a-z0-9-]+)\)/g)].map((m) => m[1]))]
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

  it('los tokens nuevos de la piel existen en claro y en oscuro', () => {
    const nuevos = ['--dax-accent-soft', '--dax-success', '--dax-warning', '--dax-danger', '--dax-on-accent']
    const lightDax = extractDaxTokens('light')
    const darkDax = extractDaxTokens('dark')
    expect(nuevos.filter((t) => !(t in lightDax))).toEqual([])
    expect(nuevos.filter((t) => !(t in darkDax))).toEqual([])
  })
})

// ── Contraste del texto sobre el acento (--dax-on-accent) ─────────────────
// El acento es el del vertical y en oscuro se aclara con color-mix hacia
// blanco, así que el color que va encima no puede ser un fijo: #fff se cae a
// ~2.9:1 en oscuro y #000 a ~2.4:1 en claro. Los valores salen de index.css
// para que la prueba no sea una segunda copia que se desalinee.

function relLuminance(hex: string): number {
  const ch = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [relLuminance(a), relLuminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

/** color-mix(in srgb, <a> <pct>%, <b>) con ambos colores opacos. */
function mixSrgb(a: string, b: string, pct: number): string {
  const chan = (h: string, i: number) => parseInt(h.slice(i, i + 2), 16)
  return '#' + [1, 3, 5]
    .map((i) => Math.round((pct * chan(a, i) + (100 - pct) * chan(b, i)) / 100))
    .map((v) => v.toString(16).padStart(2, '0'))
    .join('')
}

function daxToken(theme: 'light' | 'dark', name: string): string {
  const value = extractDaxTokens(theme)[name]
  expect(value, `falta ${name} en el tema ${theme}`).toBeTruthy()
  const m = value.match(/^(#[0-9a-fA-F]{6})$/)
  expect(m, `${name} en ${theme} no es un hex de 6 dígitos: ${value}`).toBeTruthy()
  return m![1]
}

describe('contraste del texto sobre el acento (spec §3.1)', () => {
  // El acento por default de :root; los verticales lo sobreescriben.
  const accentLight = root.match(/^\s*--p-accent:\s*(#[0-9a-fA-F]{6})/m)?.[1] ?? ''

  it('index.css define el acento por default como hex', () => {
    expect(accentLight).toMatch(/^#[0-9a-fA-F]{6}$/)
  })

  it('en claro, --dax-on-accent sobre el acento da ≥ 4.5:1', () => {
    expect(contrast(daxToken('light', '--dax-on-accent'), accentLight)).toBeGreaterThanOrEqual(4.5)
  })

  it('en oscuro, --dax-on-accent sobre el acento aclarado da ≥ 4.5:1', () => {
    // .dark aclara el acento: color-mix(in srgb, var(--p-accent) N%, #ffffff)
    const mix = extractDaxTokens('dark')['--dax-accent']
    const m = mix?.match(/color-mix\(in srgb,\s*var\(--p-accent\)\s*(\d+)%,\s*(#[0-9a-fA-F]{6})\)/)
    expect(m, `--dax-accent en oscuro no es el color-mix esperado: ${mix}`).toBeTruthy()
    const accentDark = mixSrgb(accentLight, m![2], Number(m![1]))
    expect(contrast(daxToken('dark', '--dax-on-accent'), accentDark)).toBeGreaterThanOrEqual(4.5)
  })

  it('platform-v2.css ya no pinta texto blanco fijo sobre el acento', () => {
    expect(css).not.toMatch(/#fff\b/)
    expect(css).toMatch(/var\(--dax-on-accent\)/)
  })
})
