import { describe, it, expect } from 'vitest'
import { rutaInicioPorRol } from './rutaInicio'

describe('rutaInicioPorRol', () => {
  it('el ADMINISTRADOR y el DUEÑO entran al escritorio adaptado también en teléfono', () => {
    // Ola 1 del responsivo: ya no se les desvía a /mobile/owner (la ruta y el ítem "Resumen móvil" siguen existiendo).
    expect(rutaInicioPorRol('ADMINISTRADOR', true, 'ATLAS_POS')).toBe('/hq/operations')
    expect(rutaInicioPorRol('DUEÑO', true, 'ATLAS_POS')).toBe('/hq/operations')
  })
  it('con preset ATLAS_ONE_* el dueño en teléfono cae en /home', () => {
    expect(rutaInicioPorRol('DUEÑO', true, 'ATLAS_ONE_RETAIL')).toBe('/home')
  })

  it('en escritorio el ADMINISTRADOR no cambia de destino', () => {
    expect(rutaInicioPorRol('ADMINISTRADOR', false, 'ATLAS_POS')).toBe('/hq/operations')
    expect(rutaInicioPorRol('ADMINISTRADOR', false, 'ATLAS_ONE_RETAIL')).toBe('/home')
  })

  it('los demas roles no cambian', () => {
    expect(rutaInicioPorRol('VENDEDOR', true)).toBe('/mobile/dashboard')
    expect(rutaInicioPorRol('SOPORTE_OPERATIVO', false)).toBe('/mobile/dashboard')
    expect(rutaInicioPorRol('CLIENTE', true)).toBe('/portal')
    expect(rutaInicioPorRol('CAJERO', true)).toBe('/atlas-pos')
    expect(rutaInicioPorRol(undefined, false)).toBe('/atlas-pos')
  })
})
