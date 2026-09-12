import { describe, it, expect } from 'vitest'

// Spec 2026-09-09 §3.2: tres breakpoints exactos. El test no mide píxeles,
// candadea que las reglas existan y que el de 900 px (el viejo, único) se
// haya ido para que nadie herede dos puntos de corte contradictorios.
import css from '../../styles/platform-v2.css?raw'

function media(maxWidth: number): string {
  const marker = `@media (max-width: ${maxWidth}px)`
  const start = css.indexOf(marker)
  expect(start, `falta ${marker}`).toBeGreaterThan(-1)
  // El bloque termina en la primera llave de cierre a nivel 0 tras el marcador.
  let depth = 0
  for (let i = css.indexOf('{', start); i < css.length; i++) {
    if (css[i] === '{') depth++
    if (css[i] === '}') { depth--; if (depth === 0) return css.slice(start, i + 1) }
  }
  throw new Error('bloque sin cerrar')
}

describe('breakpoints del nivel SUPERADMIN (spec §3.2)', () => {
  it('ya no existe el breakpoint único de 900 px', () => {
    expect(css.includes('@media (max-width: 900px)')).toBe(false)
  })

  it('≤1024: sidebar de 64 px solo iconos', () => {
    const b = media(1024)
    expect(b).toMatch(/\.pv2-layout\s*{\s*grid-template-columns:\s*64px 1fr/)
    expect(b).toMatch(/\.nav-item span[^}]*display:\s*none/)
  })

  it('≤768: rejillas de 2 y filtros en una fila con scroll horizontal', () => {
    const b = media(768)
    expect(b).toMatch(/grid-kpis-8\s*{\s*grid-template-columns:\s*repeat\(2, 1fr\)/)
    expect(b).toMatch(/\.pv2-filters[^}]*flex-wrap:\s*nowrap/)
    expect(b).toMatch(/\.pv2-filters[^}]*overflow-x:\s*auto/)
    expect(b).not.toMatch(/\.page-head \.right[^}]*display:\s*none/)
  })

  it('≤480: sidebar oculto y barra inferior visible', () => {
    const b = media(480)
    expect(b).toMatch(/\.pv2-sidebar\s*{[^}]*display:\s*none/)
    expect(b).toMatch(/\.pv2-bottombar\s*{[^}]*display:\s*(grid|flex)/)
    expect(b).toMatch(/\.pv2-layout\s*{\s*grid-template-columns:\s*1fr/)
  })

  it('la barra inferior está oculta por default (solo teléfono)', () => {
    expect(css).toMatch(/\.pv2-bottombar\s*{[^}]*display:\s*none/)
  })

  it('la tabla ancha tiene su propio scroll horizontal', () => {
    expect(css).toMatch(/\.pv2 \.pv2-scroll-x\s*{[^}]*overflow-x:\s*auto/)
  })
})
