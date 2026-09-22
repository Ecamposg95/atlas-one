import { describe, it, expect } from 'vitest'

import {
  estadoVenta, metodoPago, tipoMovimiento, accionBitacora, rolUsuario, estadoDevolucion,
  humanizar, ESTADOS_VENTA, METODOS_PAGO, TIPOS_MOVIMIENTO, ROLES_USUARIO,
} from './enumsEspanol'

describe('los enums que se ven en pantalla', () => {
  it('traducen el estado de la venta', () => {
    expect(estadoVenta('PAID')).toBe('Pagada')
    expect(estadoVenta('CANCELLED')).toBe('Cancelada')
    expect(estadoVenta('REFUNDED_PARTIAL')).toBe('Devuelta en parte')
  })

  it('traducen la forma de pago', () => {
    expect(metodoPago('CASH')).toBe('Efectivo')
    expect(metodoPago('CARD')).toBe('Tarjeta')
  })

  it('traducen el movimiento del kardex', () => {
    expect(tipoMovimiento('ADJUSTMENT_IN')).toBe('Ajuste (+)')
    expect(tipoMovimiento('SALE_OUT')).toBe('Venta')
  })

  it('traducen la acción de la bitácora', () => {
    expect(accionBitacora('TOGGLE_MODULE')).toBe('Módulo encendido o apagado')
    expect(accionBitacora('CREATE')).toBe('Alta')
  })

  it('traducen el rol sin guiones bajos', () => {
    expect(rolUsuario('SOPORTE_OPERATIVO')).toBe('Soporte')
    expect(rolUsuario('CAJERO')).toBe('Cajero')
  })
})

describe('los valores que no están en el diccionario', () => {
  it('se muestran legibles en vez de desaparecer', () => {
    expect(estadoVenta('ESTADO_NUEVO')).toBe('Estado nuevo')
    expect(humanizar('RECIPE_CONSUMPTION')).toBe('Recipe consumption')
  })

  it('un hueco se dibuja como raya, no como "undefined"', () => {
    expect(estadoVenta(null)).toBe('—')
    expect(metodoPago(undefined)).toBe('—')
    expect(tipoMovimiento('')).toBe('—')
  })
})

describe('los diccionarios', () => {
  it('no dejan ningún valor del backend sin traducir', () => {
    // Si el backend agrega un valor, esta lista es la que hay que ampliar.
    expect(Object.keys(ESTADOS_VENTA)).toEqual(expect.arrayContaining([
      'DRAFT', 'PENDING', 'PAID', 'CANCELLED', 'REFUNDED_PARTIAL', 'REFUNDED_TOTAL',
    ]))
    expect(Object.keys(METODOS_PAGO)).toEqual(['CASH', 'CARD', 'TRANSFER', 'OTHER'])
    expect(Object.keys(TIPOS_MOVIMIENTO)).toEqual(expect.arrayContaining([
      'PURCHASE_IN', 'SALE_OUT', 'ADJUSTMENT_IN', 'ADJUSTMENT_OUT',
      'TRANSFER_IN', 'TRANSFER_OUT', 'SALE_RETURN', 'RECIPE_CONSUMPTION',
    ]))
    expect(Object.keys(ROLES_USUARIO)).toEqual(expect.arrayContaining([
      'ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO', 'VENDEDOR', 'SOPORTE_OPERATIVO',
    ]))
  })

  it('no traducen nada al vacío', () => {
    for (const tabla of [ESTADOS_VENTA, METODOS_PAGO, TIPOS_MOVIMIENTO, ROLES_USUARIO]) {
      for (const texto of Object.values(tabla)) expect(texto.trim()).not.toBe('')
    }
  })
})

describe('el estado de una devolución', () => {
  it('se lee en español', () => {
    expect(estadoDevolucion('PENDING')).toBe('Por aprobar')
    expect(estadoDevolucion('APPROVED')).toBe('Aprobada')
    expect(estadoDevolucion('REJECTED')).toBe('Rechazada')
  })
})
