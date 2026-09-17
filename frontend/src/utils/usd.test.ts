import { describe, it, expect } from 'vitest'

import { formatUsd, usdEquivalent, usdSummary } from './usd'

// El equivalente en dólares es informativo: nunca debe producir NaN, "$NaN"
// ni un número con más de dos decimales en pantalla. Cuando no hay tipo de
// cambio, la UI no pinta nada — de ahí el `null` de `usdSummary`.

describe('usdEquivalent', () => {
  it('convierte y redondea a centavos', () => {
    expect(usdEquivalent(185, 18.5)).toBe(10)
    expect(usdEquivalent(100, 18.5)).toBe(5.41)   // 5.4054... half up
  })

  it('acepta los strings decimales que manda el backend', () => {
    expect(usdEquivalent('185.00', '18.5000')).toBe(10)
  })

  it('devuelve 0 con tipo de cambio inválido', () => {
    expect(usdEquivalent(185, 0)).toBe(0)
    expect(usdEquivalent(185, null)).toBe(0)
    expect(usdEquivalent(185, -1)).toBe(0)
    expect(usdEquivalent(185, 'abc')).toBe(0)
  })

  it('devuelve 0 con monto inválido', () => {
    expect(usdEquivalent(null, 18.5)).toBe(0)
    expect(usdEquivalent(undefined, 18.5)).toBe(0)
  })
})

describe('formatUsd', () => {
  it('no deja espacios duros en el string', () => {
    // `Intl` en es-MX separa "USD" del monto con U+00A0; se normaliza para que
    // el string sea comparable y no rompa un split/includes.
    expect(formatUsd(12.34)).toBe('USD 12.34')
    expect(formatUsd(12.34)).not.toContain(' ')
  })

  it('nunca devuelve NaN', () => {
    expect(formatUsd(null)).toBe('USD 0.00')
    expect(formatUsd('abc')).toBe('USD 0.00')
  })
})

describe('usdSummary', () => {
  it('arma la línea del carrito', () => {
    expect(usdSummary(185, 18.5)).toBe('≈ USD 10.00 · T.C. 18.50')
  })

  it('sin tipo de cambio devuelve null (no se pinta nada)', () => {
    expect(usdSummary(185, null)).toBeNull()
    expect(usdSummary(185, 0)).toBeNull()
  })
})
