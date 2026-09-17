import { describe, it, expect } from 'vitest'

import { formatPct, mixedSurcharge, surchargeFor } from './cardSurcharge'

// Espejo en pantalla de `app/services/card_surcharge.py`: los dos tienen que
// dar EXACTAMENTE el mismo centavo, porque el cajero lee uno y el backend
// cobra el otro. Con el porcentaje en 0 el resultado es neutro: `totalDue`
// es el total y todo lo demás es 0.

describe('surchargeFor', () => {
  it('sin porcentaje no cobra nada', () => {
    expect(surchargeFor(1000, 0, 0)).toEqual({
      base: 0, pct: 0, amount: 0, cardDue: 0, totalDue: 1000,
    })
    expect(surchargeFor(1000, 0, null)).toEqual({
      base: 0, pct: 0, amount: 0, cardDue: 0, totalDue: 1000,
    })
  })

  it('cobra el 100 % de la venta cuando no hay otro pago', () => {
    // Ejemplo A del diseño.
    expect(surchargeFor(1000, 0, 3.5)).toEqual({
      base: 1000, pct: 3.5, amount: 35, cardDue: 1035, totalDue: 1035,
    })
  })

  it('en un mixto solo cobra la parte de tarjeta', () => {
    // Ejemplo B del diseño.
    expect(surchargeFor(1000, 400, 3.5)).toEqual({
      base: 600, pct: 3.5, amount: 21, cardDue: 621, totalDue: 1021,
    })
  })

  it('el efectivo que cubre todo deja la base en cero', () => {
    expect(surchargeFor(1000, 1200, 3.5)).toEqual({
      base: 0, pct: 0, amount: 0, cardDue: 0, totalDue: 1000,
    })
  })

  it('redondea medio centavo hacia arriba, igual que el backend', () => {
    // Ejemplo F: 333.33 × 3.5 % = 11.66655 → 11.67
    expect(surchargeFor(333.33, 0, 3.5).amount).toBe(11.67)
    expect(surchargeFor(1, 0, 2.5).amount).toBe(0.03)   // 0.025 → 0.03
  })

  it('acepta los strings decimales que manda el backend', () => {
    expect(surchargeFor('1000.00', '400.00', '3.50').amount).toBe(21)
  })

  it('nunca devuelve NaN con entradas basura', () => {
    expect(surchargeFor(null, null, 3.5)).toEqual({
      base: 0, pct: 0, amount: 0, cardDue: 0, totalDue: 0,
    })
    expect(surchargeFor(1000, 0, 'abc').totalDue).toBe(1000)
    expect(surchargeFor(1000, 0, -3).amount).toBe(0)
  })

  it('las dos invariantes siempre valen', () => {
    for (const [total, efectivo, pct] of [[1000, 0, 3.5], [1000, 400, 3.5], [333.33, 0, 2.9], [19.99, 5, 20]]) {
      const s = surchargeFor(total, efectivo, pct)
      expect(s.totalDue).toBeCloseTo(total + s.amount, 2)
      expect(s.cardDue).toBeCloseTo(s.base + s.amount, 2)
    }
  })
})

describe('formatPct', () => {
  it('no arrastra ceros de relleno', () => {
    expect(formatPct(3.5)).toBe('3.5')
    expect(formatPct(3)).toBe('3')
    expect(formatPct(2.75)).toBe('2.75')
    expect(formatPct('20.00')).toBe('20')
  })

  it('entrada inválida devuelve 0', () => {
    expect(formatPct(null)).toBe('0')
    expect(formatPct('abc')).toBe('0')
  })
})

// El backend solo cobra comisión si la venta trae un pago con tarjeta
// (`app/services/card_surcharge.py::hay_pago_con_tarjeta`). El modal de pago
// mixto no lo comprobaba: un mixto EFECTIVO+TRANSFERENCIA mostraba "Comisión"
// y pedía de más por una comisión que nadie iba a cobrar.

describe('mixedSurcharge', () => {
  const pct = 3.5

  it('sin línea de tarjeta no cobra comisión', () => {
    const r = mixedSurcharge(1000, [
      { method: 'CASH', amount: '500' },
      { method: 'TRANSFER', amount: '514' },
    ], pct)
    expect(r.hasCard).toBe(false)
    expect(r.charged.amount).toBe(0)
    expect(r.charged.totalDue).toBe(1000)
  })

  it('sin línea de tarjeta sigue proyectando lo que costaría completarla', () => {
    // Es lo que alimenta el botón "Completar con tarjeta": justo el caso en
    // el que la línea de CARD todavía no existe.
    const r = mixedSurcharge(1000, [{ method: 'CASH', amount: '600' }], pct)
    expect(r.hasCard).toBe(false)
    expect(r.projected.amount).toBe(14)
    expect(r.projected.cardDue).toBe(414)
  })

  it('con línea de tarjeta cobra la comisión sobre lo no-tarjeta', () => {
    const r = mixedSurcharge(1000, [
      { method: 'CASH', amount: '600' },
      { method: 'CARD', amount: '517.50' },
    ], pct)
    expect(r.hasCard).toBe(true)
    expect(r.charged.amount).toBe(14)
    expect(r.charged.totalDue).toBe(1014)
    expect(r.nonCardPaid).toBe(600)
  })

  it('una línea de tarjeta vacía ya cuenta como tarjeta', () => {
    // El cajero agregó el renglón y todavía no teclea el importe: el backend
    // recibirá un pago CARD, así que la comisión que se muestra es real.
    const r = mixedSurcharge(1000, [
      { method: 'CASH', amount: '600' },
      { method: 'CARD', amount: '' },
    ], pct)
    expect(r.hasCard).toBe(true)
    expect(r.charged.amount).toBe(14)
  })

  it('con el porcentaje apagado todo es neutro', () => {
    const r = mixedSurcharge(1000, [{ method: 'CARD', amount: '1000' }], 0)
    expect(r.charged.amount).toBe(0)
    expect(r.projected.amount).toBe(0)
    expect(r.charged.totalDue).toBe(1000)
  })
})
