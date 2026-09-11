import { describe, it, expect } from 'vitest'
import { cashPaymentValidity } from '../cashPayment'

describe('cashPaymentValidity — espejo del guard de sobrepago del backend (>10x → 422)', () => {
  it('recibido menor al total: falta', () => {
    expect(cashPaymentValidity(10, 15)).toEqual({ ok: false, short: true, overpay: false })
  })
  it('exacto y con cambio razonable: ok', () => {
    expect(cashPaymentValidity(15, 15).ok).toBe(true)
    expect(cashPaymentValidity(100, 15).ok).toBe(true)
    expect(cashPaymentValidity(150, 15).ok).toBe(true) // exactamente 10x sigue siendo válido
  })
  it('más de 10 veces el total: sobrepago (el backend lo rechazaría)', () => {
    expect(cashPaymentValidity(200, 15)).toEqual({ ok: false, short: false, overpay: true })
  })
  it('total cero no dispara sobrepago', () => {
    expect(cashPaymentValidity(50, 0).overpay).toBe(false)
  })
  it('NaN o negativo cuentan como falta', () => {
    expect(cashPaymentValidity(NaN, 15).short).toBe(true)
    expect(cashPaymentValidity(-5, 15).short).toBe(true)
  })
  it('tolerancia de centavo, espejo de tolerance = Decimal("0.01") del backend: diferencia de redondeo no es falta', () => {
    expect(cashPaymentValidity(15, 15.000000001).short).toBe(false)
  })
  it('tolerancia de centavo: un centavo completo de menos sigue siendo falta', () => {
    expect(cashPaymentValidity(14.99, 15).short).toBe(true)
  })
})
