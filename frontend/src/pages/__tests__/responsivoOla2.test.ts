import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** Pantallas de la ola 2 del responsivo (catálogo y personas) y, desde SP6, todo el grupo HQ; desde la Fase 2 del admin, Reportes. */
export const PAGINAS = [
  'core/Brands.tsx', 'core/Departments.tsx', 'core/Users.tsx', 'crm/Customers.tsx', 'inventory/Inventory.tsx',
  'inventory/Products.tsx', 'hq/Inicio.tsx',
  'reports/Reportes.tsx', 'sales/SalesHistory.tsx', 'sales/Returns.tsx', 'hq/HQBranches.tsx', 'hq/HQValorInventario.tsx',
]
/** Tienen tarjetas propias y no usan TarjetaFila (HQValorInventario las delega en `components/reports/DistribucionValor`). */
export const SIN_TARJETA_FILA: string[] = ['hq/HQValorInventario.tsx']

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
  it.each(['inventory/Inventory.tsx'])('%s: las dos tablas están tras el condicional', (p) => {
    const s = fuente(p)
    expect((s.match(/<table/g) ?? []).length).toBe(2)
    expect((s.match(/esTelefono \?/g) ?? []).length).toBe(2)
  })
  it('Customers conserva la paginación fuera del condicional y usa Modal del kit para pago y formulario', () => {
    const s = fuente('crm/Customers.tsx')
    expect(s.indexOf('pages > 1')).toBeGreaterThan(s.indexOf('esTelefono ?'))
    expect(s).toMatch(/import \{ Modal \} from '\.\.\/\.\.\/components\/ui\/Modal'/)
    expect((s.match(/fixed inset-0/g) ?? []).length).toBe(1) // solo el estado de cuenta (cabecera propia)
    expect(fuente('crm/CustomerFormModal.tsx')).not.toMatch(/fixed inset-0/)
  })
})
