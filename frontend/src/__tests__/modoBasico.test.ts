import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const src = (p: string) => readFileSync(resolve(__dirname, '..', p), 'utf8')

/** Archivos nuevos del modo básico: render condicional, nunca `hidden`. Cada tarea añade los suyos. */
const NUEVOS = [
  'pages/pos/opcionesPos.ts', 'components/pos/AltaRapidaProducto.tsx', 'components/layout/navPerfilBasico.ts',
  'pages/hq/Inicio.tsx', 'pages/hq/InicioGraficas.tsx', 'components/layout/PorPerfil.tsx',
  'components/ui/MasOpciones.tsx', 'pages/platform/SelectorPerfilUi.tsx',
]

describe('modo básico: carga y render condicional', () => {
  it('el POS carga el alta (formulario único) con lazy(), sin import estático del formulario', () => {
    const pos = src('pages/pos/POS.tsx')
    expect(pos).toMatch(/lazy\(\(\) => import\('\.\.\/\.\.\/components\/pos\/AltaRapidaProducto'\)\)/)
    expect(pos).not.toMatch(/from '\.\.\/\.\.\/components\/products\/FormularioProducto'/)
    expect(pos).not.toMatch(/from '\.\.\/\.\.\/components\/pos\/AltaRapidaProducto'/)
  })

  it('el Inicio es una sola pantalla por perfil (SP6) en chunk propio sin chart.js; Reportes es una sola pantalla para todos (Fase 2)', () => {
    const app = src('App.tsx')
    expect(app).toMatch(/const Inicio\s+= lazy\(\(\) => import\('\.\/pages\/hq\/Inicio'\)/)
    expect(app).toMatch(/path="operations"[^\n]*<Inicio \/>/)
    expect(app).not.toMatch(/HQOperations|InicioBasico|HQReportsHub|finance\/Reports|PorPerfil/)
    expect(app).toMatch(/path="reports-hub"[^\n]*<Reportes conSucursales \/>/)
    expect(app).toMatch(/path="reports"\s+element=[^\n]*<Reportes \/>/)
    // El Inicio solo llega a las gráficas por lazy(): chart.js no viaja en su chunk.
    const inicio = src('pages/hq/Inicio.tsx')
    expect(inicio).not.toMatch(/chart\.js|react-chartjs-2|components\/graficas/)
    expect(inicio).toMatch(/lazy\(\(\) => import\('\.\/InicioGraficas'\)/)
    expect(inicio).not.toMatch(/^import \{[^}]*\} from '\.\/InicioGraficas'/m)   // solo `import type`
  })

  it('el alta se precarga y va dentro de un límite de error (el carrito no se pierde)', () => {
    const pos = src('pages/pos/POS.tsx')
    // SP1-c: el alta usa el formulario único en todos los perfiles; se precarga cuando el usuario puede dar de alta.
    expect(pos).toMatch(/void import\('\.\.\/\.\.\/components\/pos\/AltaRapidaProducto'\)/)
    expect(pos).toMatch(/<LimiteDeError[\s\S]*<Suspense[\s\S]*<AltaRapidaProducto[\s\S]*<\/LimiteDeError>/)
  })

  it.each(NUEVOS)('%s no esconde con la clase hidden', (p) => {
    expect(src(p)).not.toMatch(/className=["'`][^"'`]*\bhidden\b/)
  })
})
