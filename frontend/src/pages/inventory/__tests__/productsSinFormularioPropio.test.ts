import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const fuente = readFileSync(resolve(__dirname, '../Products.tsx'), 'utf8')

describe('Products.tsx: la lista no tiene formulario propio', () => {
  it('no define ProductModal ni CreateProductMiniModal', () => {
    expect(fuente).not.toMatch(/function ProductModal\b/)
    expect(fuente).not.toMatch(/CreateProductMiniModal/)
    expect(fuente).not.toMatch(/productsApi\.(create|update)\(/)
  })
  it('monta FormularioProducto dentro de Modal', () => {
    expect(fuente).toMatch(/<FormularioProducto/)
    expect(fuente).toMatch(/from '\.\.\/\.\.\/components\/ui\/Modal'/)
  })
  it('no queda la rama muerta isBranchEditor', () => {
    expect(fuente).not.toMatch(/isBranchEditor/)
  })
})
