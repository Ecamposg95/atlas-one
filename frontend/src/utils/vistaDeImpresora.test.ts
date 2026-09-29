import { describe, expect, it } from 'vitest'
import { vistaDeImpresora } from './vistaDeImpresora'

describe('vistaDeImpresora', () => {
  it('el administrador y el dueño ven la pantalla completa', () => {
    expect(vistaDeImpresora('ADMINISTRADOR')).toBe('admin')
    expect(vistaDeImpresora('DUEÑO')).toBe('admin')
  })

  it('la cajera y el gerente ven la simplificada', () => {
    expect(vistaDeImpresora('CAJERO')).toBe('cajera')
    expect(vistaDeImpresora('GERENTE')).toBe('cajera')
  })

  it('sin rol conocido, la simplificada: nunca se regala la configuración de la sucursal', () => {
    expect(vistaDeImpresora(null)).toBe('cajera')
    expect(vistaDeImpresora(undefined)).toBe('cajera')
  })
})
