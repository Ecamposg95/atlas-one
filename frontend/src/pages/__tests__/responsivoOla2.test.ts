import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** Pantallas de la ola 2 del responsivo (catálogo y personas). Cada tarea añade la suya. */
export const PAGINAS = ['core/Brands.tsx', 'core/Departments.tsx', 'core/Users.tsx']
/** Tienen tarjetas propias y no usan TarjetaFila. */
export const SIN_TARJETA_FILA: string[] = []

const fuente = (p: string) => readFileSync(resolve(__dirname, '..', p), 'utf8')
// `grid-cols-3` o más sin prefijo sm:/md:/lg:/max-*: (1 y 2 columnas sí caben en 390 px).
// Excepción explícita: la línea lleva el comentario `rejilla fija:` (N columnas cortas que caben).
const REJILLA_SIN_PREFIJO = /(?<![\w:-])grid-cols-(?:[3-9]|1[0-2])\b/
const sinExcepciones = (s: string) => s.split('\n').filter((l) => !l.includes('rejilla fija:')).join('\n')

describe('ola 2 responsiva: catálogo y personas', () => {
  it.each(PAGINAS)('%s usa el hook y el kit', (p) => {
    const s = fuente(p)
    expect(s).toMatch(/useEsTelefono\(\)/)
    expect(s).toMatch(/<CabeceraPagina/)
    if (!SIN_TARJETA_FILA.includes(p)) expect(s).toMatch(/<TarjetaFila/)
  })
  it.each(PAGINAS)('%s no tiene rejillas sin prefijo ni dos árboles montados', (p) => {
    const s = fuente(p)
    expect(sinExcepciones(s)).not.toMatch(REJILLA_SIN_PREFIJO)
    expect(s).not.toMatch(/hidden md:block|md:hidden/)
  })
})
