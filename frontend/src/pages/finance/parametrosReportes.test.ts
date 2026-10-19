import { describe, it, expect } from 'vitest'
import { parametrosReportes } from './parametrosReportes'

describe('parametrosReportes', () => {
  it('dueña en básico: org entera y semana de 7 días con hoy', () => {
    expect(parametrosReportes('basico', 'DUEÑO')).toEqual({ branch_id: 0, diasSemana: 6 })
    expect(parametrosReportes('basico', 'ADMINISTRADOR')).toEqual({ branch_id: 0, diasSemana: 6 })
  })
  it('cajera, gerente y completo no cambian', () => {
    for (const r of ['CAJERO', 'GERENTE', undefined]) expect(parametrosReportes('basico', r)).toEqual({ diasSemana: 7 })
    expect(parametrosReportes('completo', 'DUEÑO')).toEqual({ diasSemana: 7 })
  })
})
