import { describe, it, expect } from 'vitest'
import { debeCerrarSolo } from '../importacion'

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
