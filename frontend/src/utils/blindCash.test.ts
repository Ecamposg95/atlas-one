/**
 * Pruebas del conteo ciego (control anti-fraude del corte de caja).
 *
 * Antes de esta tarea, blindCash.ts se verificaba solo con `tsc` y `build`:
 * ningún caso de negocio (vacío, negativo, turno abierto/cerrado) tenía
 * cobertura. Esta suite fija el comportamiento esperado.
 */
import { describe, expect, it } from 'vitest'
import { isValidCount, shouldRevealExpected, shouldShowExpectedKpi } from './blindCash'

describe('isValidCount', () => {
  it('rechaza vacio y basura', () => {
    for (const v of ['', '   ', 'abc', '-5']) expect(isValidCount(v)).toBe(false)
  })
  it('acepta un conteo numerico, incluido el cero', () => {
    for (const v of ['0', '0.00', '1530.50']) expect(isValidCount(v)).toBe(true)
  })
})

describe('shouldRevealExpected', () => {
  it('no revela con el turno abierto aunque haya conteo', () => {
    expect(shouldRevealExpected(false)).toBe(false)
  })
  it('revela solo con el turno cerrado', () => {
    expect(shouldRevealExpected(true)).toBe(true)
  })
  it('con el conteo ciego apagado en la tienda revela aun con el turno abierto', () => {
    expect(shouldRevealExpected(false, false)).toBe(true)
    expect(shouldRevealExpected(false, true)).toBe(false)
  })
})

describe('shouldShowExpectedKpi', () => {
  it('enmascara mientras el turno esta abierto', () => {
    expect(shouldShowExpectedKpi(true)).toBe(false)
    expect(shouldShowExpectedKpi(false)).toBe(true)
  })
  it('con el conteo ciego apagado se ve con el turno abierto', () => {
    expect(shouldShowExpectedKpi(true, false)).toBe(true)
  })
})
