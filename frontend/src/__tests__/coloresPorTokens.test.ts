import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

/**
 * Tema por tokens (spec 2026-10-23 §3.4): las pantallas del admin se pintan
 * con `text-dax-*`, `bg-dax-*`, `border-dax-*` (tailwind.config.js →
 * colors.dax), nunca con `text-white`, `slate-*` ni hex sueltos: el modo claro
 * los sobrescribe con `!important` en index.css y cada color fijo es un parche
 * más. PENDIENTES es la deuda que quedó al cerrar la Fase 2 (2026-10-24); cada
 * fase la vacía. Para limpiar un archivo: quita sus colores fijos Y bórralo de
 * la lista (la segunda prueba lo exige).
 */
const raiz = resolve(__dirname, '..')
const CARPETAS = ['pages/hq', 'pages/home', 'pages/finance', 'pages/sales', 'pages/inventory', 'pages/core',
  'pages/reports', 'components/reports', 'components/graficas']
const PROHIBIDAS = /(?<![\w-])(?:text-white|text-slate-\d{2,3}|bg-slate-\d{2,3}|border-slate-\d{2,3})(?![\w-])|#[0-9a-fA-F]{6}\b/
/** Cualquier color de la paleta de Tailwind (los archivos de esta fase no usan ninguno). */
const PALETA = /(?<![\w-])(?:(?:hover|focus|active|dark|group-hover|max-md|sm|md|lg):)*(?:text|bg|border|ring|from|to|via|fill|stroke)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|white|black)(?:-\d{2,3})?(?:\/\d{1,3})?(?![\w-])/

const PENDIENTES = [
  'pages/core/AdminCatalog.tsx', 'pages/core/Brands.tsx', 'pages/core/Departments.tsx', 'pages/core/Organization.tsx',
  'pages/core/Users.tsx', 'pages/core/catalogActions.ts',
  'pages/finance/CashHistory.tsx', 'pages/finance/Expenses.tsx', 'pages/finance/Purchases.tsx',
  'pages/home/GastroHomeDay.tsx', 'pages/home/PresetHome.tsx',
  'pages/hq/HQBranches.tsx', 'pages/hq/HQInventory.tsx', 'pages/hq/HQReturns.tsx', 'pages/hq/HQSalesLog.tsx',
  'pages/inventory/Boxes.tsx', 'pages/inventory/Inventory.tsx', 'pages/inventory/Logistics.tsx', 'pages/inventory/Products.tsx',
  'pages/inventory/conteos/BuscadorVariante.tsx', 'pages/inventory/conteos/ConteoReporte.tsx', 'pages/inventory/conteos/avance.ts',
  'pages/inventory/conteos/ConteoSesion.tsx', 'pages/inventory/conteos/Conteos.tsx',
  'pages/inventory/conteos/FichaProducto.tsx', 'pages/inventory/conteos/ListaDepartamento.tsx',
  'pages/inventory/conteos/lista.ts',
  'pages/reports/Meseros.tsx',
  'pages/sales/QuoteMaker.tsx', 'pages/sales/Quotes.tsx', 'pages/sales/Returns.tsx', 'pages/sales/SalesHistory.tsx',
  'pages/sales/Seguimiento.tsx',
]
/** chart.js pinta en canvas y no entiende `var()`: `tema.ts` necesita un color concreto
 *  de respaldo por si el token falta. Es el único hex permitido en estas carpetas. */
const RESPALDOS_DEL_CANVAS = ['components/graficas/tema.ts']
/** Lo que esta fase creó o reescribió: cero colores fijos, de ninguna paleta. */
const LIMPIOS = [
  'pages/hq/Inicio.tsx', 'pages/hq/InicioGraficas.tsx', 'pages/reports/Reportes.tsx', 'pages/reports/presetsReportes.ts',
  'components/reports/Heatmap.tsx', 'components/reports/ValorTiendaCard.tsx', 'components/ui/KpiCard.tsx',
]

function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) return n === '__tests__' ? [] : archivos(p)
    return /\.tsx?$/.test(n) && !/\.test\.tsx?$/.test(n) ? [p] : []
  })
}
const relativo = (p: string) => p.slice(raiz.length + 1).replace(/\\/g, '/')
const fuente = (rel: string) => readFileSync(join(raiz, rel), 'utf8')

describe('colores por tokens (spec §3.4)', () => {
  const todos = CARPETAS.flatMap((c) => archivos(join(raiz, c))).map(relativo)

  it('ningún archivo fuera de PENDIENTES usa text-white, slate-* ni hex', () => {
    const culpables = todos.filter((f) => !PENDIENTES.includes(f) && !RESPALDOS_DEL_CANVAS.includes(f) && PROHIBIDAS.test(fuente(f)))
    expect(culpables).toEqual([])
  })

  it('todo PENDIENTES sigue sucio y existe (al limpiar o borrar un archivo, quítalo de la lista)', () => {
    const limpios = PENDIENTES.filter((f) => !todos.includes(f) || !PROHIBIDAS.test(fuente(f)))
    expect(limpios).toEqual([])
  })

  it('los archivos de la Fase 2 y el kit de gráficas no usan ninguna paleta de Tailwind', () => {
    const kit = archivos(join(raiz, 'components/graficas')).map(relativo)
    const culpables = [...LIMPIOS, ...kit]
      .map((f) => ({ f, hallazgos: fuente(f).match(new RegExp(PALETA.source, 'g')) ?? [] }))
      .filter(({ hallazgos }) => hallazgos.length > 0)
      .map(({ f, hallazgos }) => `${f}: ${[...new Set(hallazgos)].join(', ')}`)
    expect(culpables).toEqual([])
  })

  it('el modo claro no gana sobrescrituras !important nuevas', () => {
    const css = readFileSync(join(raiz, 'index.css'), 'utf8')
    const bloque = css.slice(css.indexOf('LIGHT MODE'), css.indexOf('@layer components'))
    expect(bloque.length).toBeGreaterThan(0)
    expect((bloque.match(/!important/g) ?? []).length).toBeLessThanOrEqual(30)
  })
})
