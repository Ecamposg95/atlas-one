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
    // Excepción legítima (no es el formulario de la lista/página de productos):
    //  - scanner/StoreScanner.tsx: ediciones parciales (código de barras, escalones de precio)
    // La ficha del POS (pos/modals/ProductDetailModal.tsx) es solo consulta desde SP1-c:
    // edita y da de alta con FormularioProducto (EditarProductoPos / AltaRapidaProducto).
    expect(llamadas).toEqual([
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
