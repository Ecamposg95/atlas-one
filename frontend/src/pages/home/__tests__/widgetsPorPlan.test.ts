import { describe, it, expect } from 'vitest'
import { separarWidgets, widgetVisible } from '../widgetsPorPlan'

const FREE = { clave: 'FREE', nombre: 'ONE FREE' }
const PRO = { clave: 'PRO', nombre: 'ONE PRO' }
const widgets = [
  { title: 'Inventario', module: 'inventory' },
  { title: 'Cotizaciones', module: 'quotes' },
  { title: 'Sucursales' },
]

describe('widgetVisible', () => {
  it('en FREE solo se ve el widget cuyo módulo está activo', () => {
    expect(widgetVisible({ module: 'inventory' }, FREE, ['core', 'inventory'])).toBe(true)
    expect(widgetVisible({ module: 'quotes' }, FREE, ['core', 'inventory'])).toBe(false)
  })
  it('sin módulo declarado siempre se ve', () => {
    expect(widgetVisible({}, FREE, ['core'])).toBe(true)
  })
  it('fuera de FREE se ve todo (el CTA lleva a la pantalla que avisa)', () => {
    expect(widgetVisible({ module: 'quotes' }, PRO, ['core'])).toBe(true)
  })
  it('sin plan cargado no se esconde nada', () => {
    expect(widgetVisible({ module: 'quotes' }, null, ['core'])).toBe(true)
  })
})

describe('separarWidgets', () => {
  it('reparte en visibles y ocultos conservando el orden', () => {
    const { visibles, ocultos } = separarWidgets(widgets, FREE, ['core', 'inventory'])
    expect(visibles.map((w) => w.title)).toEqual(['Inventario', 'Sucursales'])
    expect(ocultos.map((w) => w.title)).toEqual(['Cotizaciones'])
  })
  it('con todos los módulos no hay ocultos', () => {
    expect(separarWidgets(widgets, FREE, ['inventory', 'quotes']).ocultos).toEqual([])
  })
})
