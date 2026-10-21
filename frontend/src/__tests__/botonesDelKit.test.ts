import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

/**
 * Congruencia de botones (SP5 cierre): las clases `dax-btn-primary` /
 * `-secondary` / `-danger` / `-ghost` (+ `dax-btn-icon`) son la API oficial;
 * `ui/Button` es solo un envoltorio de esas clases. No hay codemod: esta
 * guardia impide que vuelvan `dax-btn` a secas (no existe en CSS) y que las
 * pantallas de la ola 3 estilicen botones con `style={{`.
 */
const raiz = resolve(__dirname, '..')
const css = readFileSync(join(raiz, 'index.css'), 'utf8')
function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) return n === '__tests__' ? [] : archivos(p)
    return /\.tsx$/.test(n) && !/\.test\.tsx$/.test(n) ? [p] : []
  })
}
const PAGINAS_OLA3 = ['pages/finance/Expenses.tsx', 'pages/finance/Purchases.tsx', 'pages/hr/HR.tsx', 'pages/inventory/Boxes.tsx',
  'pages/inventory/Logistics.tsx', 'pages/sales/Quotes.tsx', 'pages/sales/Seguimiento.tsx']

describe('botones del kit: dax-btn-* es la API', () => {
  it('las cuatro variantes existen en index.css (ghost incluida)', () => {
    for (const v of ['primary', 'secondary', 'danger', 'ghost']) expect(css, v).toMatch(new RegExp(`\\.dax-btn-${v}\\s*\\{`))
  })
  it('ui/Button mapea a las clases y no duplica el padding en md', () => {
    const s = readFileSync(join(raiz, 'components/ui/Button.tsx'), 'utf8')
    expect(s).toMatch(/ghost: 'dax-btn-ghost'/)
    expect(s).toMatch(/md: ''/)
  })
  it('ningún archivo usa la clase `dax-btn` a secas (no existe en CSS)', () => {
    const culpables = archivos(raiz)
      .filter((f) => /["'`\s]dax-btn(?![-\w])/.test(readFileSync(f, 'utf8')))
      .map((f) => f.replace(raiz, ''))
    expect(culpables).toEqual([])
  })
  it('las pantallas de la ola 3 no estilizan botones con style={{', () => {
    for (const p of PAGINAS_OLA3) {
      const s = readFileSync(join(raiz, p), 'utf8')
      expect(s, p).not.toMatch(/<(button|a)\b[^>]*style=\{\{/s)
    }
  })
})
