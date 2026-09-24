import { describe, expect, it } from 'vitest'
import { puede } from './capacidades'

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
