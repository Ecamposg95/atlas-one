import { describe, expect, it } from 'vitest'
import { medidasReducidas, sirveSinTocar } from './comprimirImagen'

describe('medidasReducidas', () => {
  it('reduce el lado mayor a 1600 y conserva la proporción', () => {
    expect(medidasReducidas(4032, 3024)).toEqual({ ancho: 1600, alto: 1200 })
    expect(medidasReducidas(3024, 4032)).toEqual({ ancho: 1200, alto: 1600 })
  })
  it('nunca agranda una foto chica', () => {
    expect(medidasReducidas(800, 600)).toEqual({ ancho: 800, alto: 600 })
  })
})

describe('sirveSinTocar', () => {
  it('deja pasar un JPEG ligero', () => {
    expect(sirveSinTocar('image/jpeg', 200_000)).toBe(true)
  })
  it('comprime fotos pesadas, HEIC y PNG', () => {
    expect(sirveSinTocar('image/jpeg', 4_000_000)).toBe(false)
    expect(sirveSinTocar('image/heic', 100_000)).toBe(false)
    expect(sirveSinTocar('image/png', 100_000)).toBe(false)
  })
})
