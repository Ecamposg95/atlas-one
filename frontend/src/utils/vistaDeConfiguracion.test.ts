import { describe, expect, it } from 'vitest'
import { vistaDeConfiguracion } from './vistaDeConfiguracion'

describe('vistaDeConfiguracion', () => {
  it('quien responde por la sucursal ve la pantalla completa', () => {
    expect(vistaDeConfiguracion('ADMINISTRADOR')).toBe('completa')
    expect(vistaDeConfiguracion('DUEÑO')).toBe('completa')
    expect(vistaDeConfiguracion('GERENTE')).toBe('completa')
  })

  it('la cajera ve la de caja', () => {
    expect(vistaDeConfiguracion('CAJERO')).toBe('caja')
  })

  it('sin rol conocido, la de caja: nunca se regala la configuración de la sucursal', () => {
    expect(vistaDeConfiguracion(null)).toBe('caja')
    expect(vistaDeConfiguracion(undefined)).toBe('caja')
  })
})
