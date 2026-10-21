import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

/**
 * SP6: el grupo HQ se pinta con el kit y clases, no con `style={{}}`. La única
 * excepción es una barra cuyo ancho ES el dato, marcada en la misma línea con
 * el comentario `estilo dinámico`. Para colorear, usa `text-dax-muted`,
 * `border-dax-border-dim`, etc. (tailwind.config.js → colors.dax).
 */
const dir = resolve(__dirname, '..', 'hq')
const paginas = readdirSync(dir).filter((n) => n.endsWith('.tsx'))

describe('pages/hq sin estilos inline', () => {
  it.each(paginas)('%s', (nombre) => {
    const lineas = readFileSync(join(dir, nombre), 'utf8').split('\n')
    const culpables = lineas
      .map((l, i) => ({ l, n: i + 1 }))
      .filter(({ l }) => l.includes('style={{') && !l.includes('estilo dinámico'))
      .map(({ l, n }) => `${n}: ${l.trim()}`)
    expect(culpables).toEqual([])
  })
})
