import { describe, it, expect } from 'vitest'
import {
  AVANZADOS_VACIOS, contarAvanzados, hayAvanzados, hoyLocal, inicioDelDiaIso, paramsAvanzados,
} from '../filtrosAvanzadosProductos'

describe('filtros avanzados de Productos', () => {
  it('vacíos: no cuentan ni viajan', () => {
    expect(contarAvanzados(AVANZADOS_VACIOS)).toBe(0)
    expect(hayAvanzados(AVANZADOS_VACIOS)).toBe(false)
    expect(paramsAvanzados(AVANZADOS_VACIOS)).toEqual({})
  })

  it('cuenta cada eje puesto, la existencia incluida', () => {
    const f = { gender: 'MUJER', size: 'M', color: '', only_with_stock: true, created_after: '2026-11-03' }
    expect(contarAvanzados(f)).toBe(4)
    expect(hayAvanzados(f)).toBe(true)
  })

  it('arma los query params; la fecha va como medianoche LOCAL en ISO', () => {
    const f = { gender: 'HOMBRE', size: ' 32 ', color: 'Negro', only_with_stock: true, created_after: '2026-11-03' }
    expect(paramsAvanzados(f)).toEqual({
      gender: 'HOMBRE', size: '32', color: 'Negro', only_with_stock: true,
      created_after: new Date(2026, 10, 3, 0, 0, 0, 0).toISOString(),
    })
  })

  it('una fecha mal formada no filtra', () => {
    expect(inicioDelDiaIso('03/11/2026')).toBeNull()
    expect(paramsAvanzados({ ...AVANZADOS_VACIOS, created_after: 'ayer' })).toEqual({})
  })

  it('hoyLocal escribe la fecha como el input date', () => {
    expect(hoyLocal(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05')
  })
})
