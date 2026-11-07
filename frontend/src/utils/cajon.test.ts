// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import {
  debeAbrirCajonSinTicket, guardarCajonAlCobrar, impresoraEfectiva, leerCajonAlCobrar, motivoSinCajon, pagoIncluyeEfectivo,
} from './cajon'

describe('motivoSinCajon', () => {
  it('explica por qué no se puede', () => {
    expect(motivoSinCajon('POS-80', false)).toMatch(/agente/)
    expect(motivoSinCajon(null, true)).toMatch(/impresora/)
    expect(motivoSinCajon('BT:PT-210', true)).toMatch(/Bluetooth/)
  })

  it('sin motivo cuando hay impresora y el agente responde o sigue comprobándose', () => {
    expect(motivoSinCajon('POS-80', true)).toBeNull()
    expect(motivoSinCajon('POS-80', null)).toBeNull()
  })
})

describe('impresoraEfectiva', () => {
  it('manda la de esta PC; la de la sucursal es el respaldo', () => {
    expect(impresoraEfectiva('POS-80', 'Zebra')).toBe('POS-80')
    expect(impresoraEfectiva(null, 'Zebra')).toBe('Zebra')
    expect(impresoraEfectiva('', 'Zebra')).toBe('Zebra')
    expect(impresoraEfectiva(null, null)).toBeNull()
  })
})

describe('pagoIncluyeEfectivo', () => {
  it('reconoce el efectivo en cualquier combinación', () => {
    expect(pagoIncluyeEfectivo([{ method: 'CASH' }])).toBe(true)
    expect(pagoIncluyeEfectivo([{ method: 'CARD' }, { method: 'efectivo' }])).toBe(true)
  })

  it('tarjeta, transferencia o fiado sin pagos no cuentan', () => {
    expect(pagoIncluyeEfectivo([{ method: 'CARD' }, { method: 'TRANSFER' }])).toBe(false)
    expect(pagoIncluyeEfectivo([])).toBe(false)
    expect(pagoIncluyeEfectivo([{}])).toBe(false)
  })
})

describe('debeAbrirCajonSinTicket', () => {
  const base = { pagos: [{ method: 'CASH' }], impresora: 'POS-80', abreAlCobrar: true }

  it('abre con efectivo, impresora e interruptor encendido', () => {
    expect(debeAbrirCajonSinTicket(base)).toBe(true)
  })

  it('no abre si falta cualquiera', () => {
    expect(debeAbrirCajonSinTicket({ ...base, pagos: [{ method: 'CARD' }] })).toBe(false)
    expect(debeAbrirCajonSinTicket({ ...base, impresora: null })).toBe(false)
    expect(debeAbrirCajonSinTicket({ ...base, impresora: 'BT:PT-210' })).toBe(false)
    expect(debeAbrirCajonSinTicket({ ...base, abreAlCobrar: false })).toBe(false)
  })
})

describe('interruptor recordado', () => {
  beforeEach(() => localStorage.clear())

  it('sin dato vale encendido, como la columna', () => {
    expect(leerCajonAlCobrar(7)).toBe(true)
    expect(leerCajonAlCobrar(null)).toBe(true)
  })

  it('se recuerda por sucursal', () => {
    guardarCajonAlCobrar(7, false)
    expect(leerCajonAlCobrar(7)).toBe(false)
    expect(leerCajonAlCobrar(8)).toBe(true)
    guardarCajonAlCobrar(7, true)
    expect(leerCajonAlCobrar(7)).toBe(true)
  })
})
