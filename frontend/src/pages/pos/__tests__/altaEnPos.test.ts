import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Guardia de fuente (SP1-c): POS.tsx es demasiado pesado para montarlo; lo que
// se fija aquí es que el alta y la edición pasen SIEMPRE por el formulario único.
const pos = readFileSync(resolve(__dirname, '../POS.tsx'), 'utf8')

describe('alta y edición de producto en el POS (SP1-c)', () => {
  it('el POS ya no importa la ficha vieja ni decide el alta por perfil', () => {
    expect(pos).not.toMatch(/ProductDetailModal/)
    expect(pos).not.toMatch(/altaCorta/)
  })

  it('AltaRapidaProducto y EditarProductoPos van por lazy() con precarga y límite de error', () => {
    expect(pos).toMatch(/lazy\(\(\) => import\('\.\.\/\.\.\/components\/pos\/AltaRapidaProducto'\)\)/)
    expect(pos).toMatch(/import\('\.\.\/\.\.\/components\/pos\/EditarProductoPos'\)/)
    expect((pos.match(/<LimiteDeError/g) ?? []).length).toBeGreaterThanOrEqual(1)
  })
})
