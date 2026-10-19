import { describe, it, expect } from 'vitest'
import { campoVisible, leerCamposProducto, TODO_VISIBLE } from '../camposProducto'

describe('campoVisible', () => {
  const pos = { visibles: ['name', 'sku'], ocultos: ['gender', 'model', 'material'] }

  it('esconde la ficha boutique cuando el giro la oculta', () => {
    expect(campoVisible(pos, 'gender')).toBe(false)
    expect(campoVisible(pos, 'model', '')).toBe(false)
  })

  it('nada se apaga: un producto que ya trae el valor lo sigue mostrando', () => {
    expect(campoVisible(pos, 'gender', 'MUJER')).toBe(true)
    expect(campoVisible(pos, 'material', '  piel ')).toBe(true)
  })

  it('lo que no está en ocultos se ve', () => {
    expect(campoVisible(pos, 'price')).toBe(true)
    expect(campoVisible(TODO_VISIBLE, 'gender')).toBe(true)
  })
})

describe('leerCamposProducto', () => {
  it('falla abierto si el contexto no trae el campo o viene roto', () => {
    expect(leerCamposProducto(undefined)).toEqual(TODO_VISIBLE)
    expect(leerCamposProducto({ visibles: 'x' })).toEqual(TODO_VISIBLE)
  })
  it('acepta la forma del servidor', () => {
    expect(leerCamposProducto({ visibles: ['name'], ocultos: ['gender'] }))
      .toEqual({ visibles: ['name'], ocultos: ['gender'] })
  })
})
