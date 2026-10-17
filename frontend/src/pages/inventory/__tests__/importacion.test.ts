import { describe, it, expect } from 'vitest'
import { cerrarImportacion, debeCerrarSolo } from '../importacion'

describe('debeCerrarSolo', () => {
  it('cierra cuando todo entró sin errores', () => {
    expect(debeCerrarSolo({ created: 3, updated: 0, errors: [] })).toBe(true)
  })
  it('se queda abierto si hubo errores por fila, aunque algo haya entrado', () => {
    expect(debeCerrarSolo({ created: 2, updated: 0, errors: ['Fila 3: precio 0'] })).toBe(false)
  })
  it('se queda abierto si no entró nada', () => {
    expect(debeCerrarSolo({ created: 0, updated: 0 })).toBe(false)
  })
})

describe('cerrarImportacion', () => {
  it('recarga si entró algo, aunque haya errores', () => {
    expect(cerrarImportacion({ created: 2, updated: 0 })).toBe('recargar')
    expect(cerrarImportacion({ created: 0, updated: 1 })).toBe('recargar')
  })
  it('solo cierra si no entró nada o no hubo carga', () => {
    expect(cerrarImportacion({ created: 0, updated: 0 })).toBe('cerrar')
    expect(cerrarImportacion(null)).toBe('cerrar')
  })
})
