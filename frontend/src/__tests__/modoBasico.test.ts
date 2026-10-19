import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const src = (p: string) => readFileSync(resolve(__dirname, '..', p), 'utf8')

/** Archivos nuevos del modo básico: render condicional, nunca `hidden`. Cada tarea añade los suyos. */
const NUEVOS = ['pages/pos/opcionesPos.ts', 'components/pos/AltaRapidaProducto.tsx', 'components/layout/navPerfilBasico.ts']

describe('modo básico: carga y render condicional', () => {
  it('el POS carga el alta corta con lazy(), sin import estático del formulario', () => {
    const pos = src('pages/pos/POS.tsx')
    expect(pos).toMatch(/lazy\(\(\) => import\('\.\.\/\.\.\/components\/pos\/AltaRapidaProducto'\)\)/)
    expect(pos).not.toMatch(/from '\.\.\/\.\.\/components\/products\/FormularioProducto'/)
    expect(pos).not.toMatch(/from '\.\.\/\.\.\/components\/pos\/AltaRapidaProducto'/)
  })

  it.each(NUEVOS)('%s no esconde con la clase hidden', (p) => {
    expect(src(p)).not.toMatch(/className=["'`][^"'`]*\bhidden\b/)
  })
})
