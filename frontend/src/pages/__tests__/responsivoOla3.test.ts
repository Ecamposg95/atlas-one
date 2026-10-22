import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** Pantallas de la ola 3 del responsivo (spec 2026-09-30 §5): el resto del admin. */
export const PAGINAS_OLA3 = ['finance/Expenses.tsx', 'finance/Purchases.tsx', 'hr/HR.tsx', 'inventory/Boxes.tsx',
  'inventory/Logistics.tsx', 'sales/Quotes.tsx', 'sales/Seguimiento.tsx']
/** Detalle con líneas: tabla en escritorio, lista en teléfono (criterio §6.2). */
const CON_DETALLE = ['finance/Purchases.tsx', 'sales/Quotes.tsx', 'sales/Seguimiento.tsx']

const fuente = (p: string) => readFileSync(resolve(__dirname, '..', p), 'utf8')
// `grid-cols-3` o más sin prefijo sm:/md:/lg:/max-*: (1 y 2 columnas sí caben en 390 px).
// Excepción explícita: la línea lleva el comentario `rejilla fija:` (N columnas cortas que caben).
const REJILLA_SIN_PREFIJO = /(?<![\w:-])grid-cols-(?:[3-9]|1[0-2])\b/
const sinExcepciones = (s: string) => s.split('\n').filter((l) => !l.includes('rejilla fija:')).join('\n')

describe('ola 3 responsiva: el resto del admin', () => {
  it.each(PAGINAS_OLA3)('%s usa el hook, el kit y Modal', (p) => {
    const s = fuente(p)
    expect(s).toMatch(/useEsTelefono\(\)/)
    expect(s).toMatch(/<CabeceraPagina/)
    expect(s).toMatch(/<TarjetaFila/)
    expect(s).toMatch(/import \{ Modal \} from '\.\.\/\.\.\/components\/ui\/Modal'/)
    expect(s).not.toMatch(/fixed inset-0/)
  })
  it.each(PAGINAS_OLA3)('%s no tiene rejillas sin prefijo ni dos árboles montados', (p) => {
    const s = fuente(p)
    expect(sinExcepciones(s)).not.toMatch(REJILLA_SIN_PREFIJO)
    expect(s).not.toMatch(/hidden md:block|md:hidden/)
  })
  it.each(CON_DETALLE)('%s: la tabla de líneas del detalle solo en escritorio', (p) => {
    const s = fuente(p)
    expect((s.match(/<table/g) ?? []).length).toBe(2)
    expect((s.match(/esTelefono \?/g) ?? []).length).toBe(2)
  })
})
