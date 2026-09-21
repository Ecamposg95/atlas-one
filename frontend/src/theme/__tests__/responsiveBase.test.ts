import { describe, it, expect } from 'vitest'

// Base responsiva (plan 2026-09-21 §Task 1). Candado sobre las reglas
// globales de las que dependen las olas 2 y 3: si alguien quita el molde de
// modales o el tamaño de los inputs, estas pruebas lo dicen. El CSS entra como
// texto (`?raw`, Vite): el proyecto no tiene @types/node, así que las pruebas
// de estilos leen archivos por el bundler y no por `node:fs`.
import css from '../../index.css?raw'

/** Bloque `@media …` completo, desde el marcador hasta su llave de cierre. */
function media(marker: string): string {
  const start = css.indexOf(marker)
  expect(start, `falta ${marker}`).toBeGreaterThan(-1)
  let depth = 0
  for (let i = css.indexOf('{', start); i < css.length; i++) {
    if (css[i] === '{') depth++
    if (css[i] === '}') { depth--; if (depth === 0) return css.slice(start, i + 1) }
  }
  throw new Error('bloque sin cerrar')
}

describe('inputs sin el zoom automático de iOS', () => {
  const b = media('@media (pointer: coarse) and (max-width: 1023px)')

  it('sube los campos a 16px en pantalla táctil por debajo de 1024', () => {
    expect(b).toMatch(/\.dax-input[^}]*font-size:\s*16px/)
    expect(b).toMatch(/textarea/)
    expect(b).toMatch(/select/)
  })

  it('no toca casillas ni radios, donde font-size solo deformaría el control', () => {
    expect(b).toMatch(/:not\(\[type='checkbox'\]\)/)
    expect(b).toMatch(/:not\(\[type='radio'\]\)/)
  })

  it('no aplica en escritorio: el corte es táctil Y < 1024', () => {
    expect(b.startsWith('@media (pointer: coarse) and (max-width: 1023px)')).toBe(true)
  })
})

describe('molde de modales .dax-modal', () => {
  it('acota el alto a 90dvh y desplaza por dentro', () => {
    const base = css.slice(css.indexOf('\n.dax-modal {'))
    expect(base).toMatch(/max-height:\s*90dvh/)
    expect(base).toMatch(/overflow-y:\s*auto/)
    expect(base).toMatch(/overscroll-behavior:\s*contain/)
  })

  it('por debajo de sm es hoja inferior con safe-area', () => {
    const b = media('@media (max-width: 639px)')
    expect(b).toMatch(/\.dax-modal\s*{/)
    expect(b).toMatch(/position:\s*fixed/)
    expect(b).toMatch(/bottom:\s*0/)
    expect(b).toMatch(/border-radius:\s*16px 16px 0 0/)
    expect(b).toMatch(/env\(safe-area-inset-bottom/)
  })

  it('ofrece un pie pegado para los botones de acción', () => {
    expect(css).toMatch(/\.dax-modal-footer\s*{[^}]*position:\s*sticky/)
  })
})

describe('alturas de pantalla completa', () => {
  it('el body mide en dvh, no en vh', () => {
    expect(css).toMatch(/min-height:\s*100dvh/)
    expect(css).not.toMatch(/min-height:\s*100vh/)
  })
})
