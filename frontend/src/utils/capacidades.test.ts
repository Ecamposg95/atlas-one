import { describe, expect, it } from 'vitest'
import { puede, saneaCobro } from './capacidades'

describe('puede', () => {
  it('deja pasar lo que la tienda tiene', () => {
    expect(puede(['propina', 'factura'], 'propina')).toBe(true)
  })

  it('bloquea lo que la tienda no tiene', () => {
    expect(puede(['factura'], 'propina')).toBe(false)
  })

  it('con la lista vacía no deja pasar nada', () => {
    // La lista vacía es una respuesta legítima del servidor: la tienda no tiene
    // ninguna función apagable encendida. No es "todavía no cargó".
    expect(puede([], 'propina')).toBe(false)
  })
})

describe('saneaCobro', () => {
  const base = { items: [], requires_invoice: true, tip_amount: 50 }

  it('borra la factura y la propina que la tienda no contrató', () => {
    expect(saneaCobro(base, false, false)).toEqual({
      items: [], requires_invoice: false, tip_amount: 0,
    })
  })

  it('no toca el cobro de una tienda que sí las contrató', () => {
    expect(saneaCobro(base, true, true)).toEqual(base)
  })

  it('deja el resto del cobro intacto', () => {
    const p = { items: [1], payments: [{ amount: 10 }], requires_invoice: false, tip_amount: 0 }
    expect(saneaCobro(p, true, true)).toEqual(p)
  })

  it('una propina ilegible cuenta como cero, no como NaN', () => {
    expect(saneaCobro({ tip_amount: undefined }, true, true).tip_amount).toBe(0)
  })
})
