import { describe, expect, it } from 'vitest'

import { FILTROS_VACIOS, filtrosActivos } from './FiltrosEtiquetas'

describe('filtrosActivos', () => {
  it('sin nada capturado no hay filtros que limpiar', () => {
    expect(filtrosActivos(FILTROS_VACIOS)).toBe(false)
  })

  it('cualquier eje capturado cuenta, incluida la casilla y la fecha', () => {
    expect(filtrosActivos({ ...FILTROS_VACIOS, search: 'camisa' })).toBe(true)
    expect(filtrosActivos({ ...FILTROS_VACIOS, department_id: 'd1' })).toBe(true)
    expect(filtrosActivos({ ...FILTROS_VACIOS, brand_id: 'b1' })).toBe(true)
    expect(filtrosActivos({ ...FILTROS_VACIOS, gender: 'HOMBRE' })).toBe(true)
    expect(filtrosActivos({ ...FILTROS_VACIOS, only_with_stock: true })).toBe(true)
    expect(filtrosActivos({ ...FILTROS_VACIOS, created_after: '2026-10-23T09:00' })).toBe(true)
  })

  it('una búsqueda de puros espacios no es un filtro', () => {
    expect(filtrosActivos({ ...FILTROS_VACIOS, search: '   ' })).toBe(false)
  })
})
