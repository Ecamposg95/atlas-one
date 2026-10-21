import { describe, it, expect } from 'vitest'
import { opcionesPorPerfil } from '../opcionesPos'

describe('opcionesPorPerfil', () => {
  it('completo: todo como hoy', () => {
    expect(opcionesPorPerfil('completo')).toEqual({
      descuentos: true, cliente: true, usd: true, editarProducto: true, forzarPieza: true,
    })
  })

  it('básico: sin descuentos, cliente, dólares, edición de producto ni forzar pieza', () => {
    expect(opcionesPorPerfil('basico')).toEqual({
      descuentos: false, cliente: false, usd: false, editarProducto: false, forzarPieza: false,
    })
  })

  it('sin perfil (contexto sin cargar) = completo', () => {
    expect(opcionesPorPerfil(null)).toEqual(opcionesPorPerfil('completo'))
    expect(opcionesPorPerfil(undefined)).toEqual(opcionesPorPerfil('completo'))
  })

  it('devuelve una copia: mutarla no cambia la siguiente llamada', () => {
    const o = opcionesPorPerfil('basico')
    o.descuentos = true
    expect(opcionesPorPerfil('basico').descuentos).toBe(false)
  })
})
