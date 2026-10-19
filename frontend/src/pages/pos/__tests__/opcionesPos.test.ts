import { describe, it, expect } from 'vitest'
import { opcionesPorPerfil } from '../opcionesPos'

describe('opcionesPorPerfil', () => {
  it('completo: todo como hoy y alta con la ficha de siempre', () => {
    expect(opcionesPorPerfil('completo')).toEqual({
      descuentos: true, cliente: true, usd: true, editarProducto: true, forzarPieza: true, altaCorta: false,
    })
  })

  it('básico: sin descuentos, cliente, dólares, edición de producto ni forzar pieza; alta corta', () => {
    expect(opcionesPorPerfil('basico')).toEqual({
      descuentos: false, cliente: false, usd: false, editarProducto: false, forzarPieza: false, altaCorta: true,
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
