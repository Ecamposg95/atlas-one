import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const raiz = resolve(__dirname, '..')
function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) return n === '__tests__' ? [] : archivos(p)
    return /\.(ts|tsx)$/.test(n) && !/\.test\.tsx?$/.test(n) ? [p] : []
  })
}

describe('un solo formulario de producto', () => {
  const llamadas = archivos(raiz).flatMap((f) => {
    const s = readFileSync(f, 'utf8')
    const n = (s.match(/productsApi\.(create|update)\(/g) ?? []).length
    return n > 0 ? [[f.replace(raiz, ''), n] as const] : []
  })
  it('solo FormularioProducto llama a productsApi.create/update', () => {
    // Excepciones legítimas (no son el formulario de la lista/página de productos):
    //  - pos/modals/ProductDetailModal.tsx: ficha de producto dentro del POS (alta/edición rápida)
    //  - scanner/StoreScanner.tsx: ediciones parciales (código de barras, escalones de precio)
    expect(llamadas).toEqual([
      ['/components/pos/modals/ProductDetailModal.tsx', 2],
      ['/components/products/FormularioProducto.tsx', 2],
      ['/pages/scanner/StoreScanner.tsx', 3],
    ])
  })
  it('los formularios viejos ya no existen', () => {
    const todo = archivos(raiz).map((f) => readFileSync(f, 'utf8')).join('\n')
    expect(todo).not.toMatch(/function ProductFormModal\b/)
    expect(todo).not.toMatch(/function ProductModal\b/)
    expect(todo).not.toMatch(/AdminProductCreate/)
  })
})
