import { describe, it, expect } from 'vitest'

import { computeAdjustment } from '../stockAdjust'

// `POST /api/inventory/adjust` recibe un DELTA (positivo entrada, negativo
// salida — app/schemas/inventory.py). En el pasillo el admin cuenta un
// ABSOLUTO: "hay 37". Traducir mal ese número mueve el inventario al revés,
// y el movimiento queda firmado con su nombre en el kardex.

describe('computeAdjustment', () => {
  it('contar menos de lo que hay es una salida', () => {
    expect(computeAdjustment(42, 37)).toEqual({ delta: -5, kind: 'salida', abs: 5 })
  })

  it('contar más de lo que hay es una entrada', () => {
    expect(computeAdjustment(10, 13)).toEqual({ delta: 3, kind: 'entrada', abs: 3 })
  })

  it('contar lo mismo no genera movimiento', () => {
    expect(computeAdjustment(20, 20)).toEqual({ delta: 0, kind: 'sin-cambio', abs: 0 })
  })

  it('cuenta desde cero', () => {
    expect(computeAdjustment(0, 8)).toEqual({ delta: 8, kind: 'entrada', abs: 8 })
  })

  it('dejar el anaquel en cero es una salida por todo lo que había', () => {
    expect(computeAdjustment(15, 0)).toEqual({ delta: -15, kind: 'salida', abs: 15 })
  })

  it('acepta decimales sin arrastrar error de punto flotante', () => {
    // 2.5 kg contra 2.1 kg: 0.4, no 0.39999999999999997.
    expect(computeAdjustment(2.5, 2.1)?.delta).toBe(-0.4)
  })

  it('trata como cero un stock actual nulo', () => {
    expect(computeAdjustment(null, 5)).toEqual({ delta: 5, kind: 'entrada', abs: 5 })
  })

  it('devuelve null si lo contado no es un número válido', () => {
    // Nunca mandar un movimiento a partir de un campo vacío o basura.
    expect(computeAdjustment(10, Number.NaN)).toBeNull()
  })

  it('devuelve null si lo contado es negativo', () => {
    expect(computeAdjustment(10, -3)).toBeNull()
  })
})
