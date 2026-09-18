import { describe, it, expect } from 'vitest'

import { usesColors, variantLabel, variantWords } from '../variantWords'

describe('usesColors', () => {
  it('es falso cuando ninguna variante trae color', () => {
    expect(usesColors([{ size: 'Ch' }, { size: 'M', color: '' }])).toBe(false)
    expect(usesColors([{ size: 'M', color: '  ' }])).toBe(false)
    expect(usesColors([])).toBe(false)
    expect(usesColors(undefined)).toBe(false)
  })
  it('es verdadero con una sola variante de color', () => {
    expect(usesColors([{ size: 'Ch' }, { color: 'Rojo', size: 'M' }])).toBe(true)
  })
})

describe('variantWords', () => {
  it('sin colores habla de tallas', () => {
    expect(variantWords(false)).toEqual({ singular: 'talla', plural: 'tallas' })
  })
  it('con colores habla de variantes', () => {
    expect(variantWords(true)).toEqual({ singular: 'variante', plural: 'variantes' })
  })
})

describe('variantLabel', () => {
  it('usa color y talla cuando los hay', () => {
    expect(variantLabel({ color: 'Rojo', size: 'M' }, 'Blusa')).toBe('Rojo / M')
    expect(variantLabel({ size: 'Ch' }, 'Blusa')).toBe('Ch')
    expect(variantLabel({ color: 'Negro' }, 'Blusa')).toBe('Negro')
  })
  it('nunca muestra "Estándar": ahí va el nombre del producto', () => {
    expect(variantLabel({ variant_name: 'Estándar' }, 'Blusa')).toBe('Blusa')
    expect(variantLabel({ variant_name: 'estandar' }, 'Blusa')).toBe('Blusa')
    expect(variantLabel({}, 'Blusa')).toBe('Blusa')
    expect(variantLabel(null, 'Blusa')).toBe('Blusa')
  })
  it('respeta un variant_name propio del negocio', () => {
    expect(variantLabel({ variant_name: 'Paquete 6' }, 'Refresco')).toBe('Paquete 6')
  })
  it('sin nombre de producto no se queda en blanco', () => {
    expect(variantLabel({ variant_name: 'Estándar' }, '  ')).toBe('Producto')
  })
})
