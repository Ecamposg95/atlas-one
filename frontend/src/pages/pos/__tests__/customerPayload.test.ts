import { describe, it, expect } from 'vitest'
import { customerFields, customerFromCartJson } from '../customerPayload'

describe('customerFields', () => {
  it('sin cliente no manda ninguna llave', () => {
    expect(customerFields(null, null)).toEqual({})
    expect(customerFields(null, '   ')).toEqual({})
  })
  it('nombre libre viaja recortado y sin customer_id', () => {
    expect(customerFields(null, '  Sr. Estadounidense ')).toEqual({ customer_name: 'Sr. Estadounidense' })
  })
  it('cliente de CRM manda id y nombre', () => {
    expect(customerFields(7, 'Patricio Pérez')).toEqual({ customer_id: 7, customer_name: 'Patricio Pérez' })
  })
  it('cliente de CRM sin nombre en memoria manda solo el id', () => {
    expect(customerFields(7, null)).toEqual({ customer_id: 7 })
  })
})

describe('customerFromCartJson', () => {
  it('restaura nombre libre guardado al pausar', () => {
    expect(customerFromCartJson({ customer_name: 'Patricio' }, null)).toEqual({ id: null, name: 'Patricio' })
  })
  it('restaura id del parked y nombre del snapshot', () => {
    expect(customerFromCartJson({ customer_name: 'Ana' }, 3)).toEqual({ id: 3, name: 'Ana' })
  })
  it('sin nada devuelve null', () => {
    expect(customerFromCartJson({}, null)).toBeNull()
    expect(customerFromCartJson({ customer_name: 42 }, null)).toBeNull()
  })
})
