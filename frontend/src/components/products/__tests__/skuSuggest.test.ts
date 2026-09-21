import { describe, it, expect } from 'vitest'

import { argsSugerencia, mensajeSugerencia, nombreDeMarca } from '../skuSuggest'

const MARCAS = [
  { id: 'b1', name: 'Louis Vuitton' },
  { id: 'b2', name: 'Gucci' },
]

describe('nombreDeMarca', () => {
  it('traduce el id a nombre', () => {
    expect(nombreDeMarca(MARCAS, 'b2')).toBe('Gucci')
  })
  it('sin marca (o con un id que ya no existe) es cadena vacía', () => {
    expect(nombreDeMarca(MARCAS, '')).toBe('')
    expect(nombreDeMarca(MARCAS, null)).toBe('')
    expect(nombreDeMarca(MARCAS, 'fantasma')).toBe('')
  })
})

describe('argsSugerencia', () => {
  it('toma color y talla de la PRIMERA fila de la matriz', () => {
    const args = argsSugerencia(
      { name: ' Chamarra ', model: ' mezclilla ', brand_id: 'b1' },
      MARCAS,
      [{ color: 'Beige', size: 'M' }, { color: 'Beige', size: 'L' }],
    )
    expect(args).toEqual({
      name: 'Chamarra', brand: 'Louis Vuitton', model: 'mezclilla',
      color: 'Beige', size: 'M',
    })
  })
  it('sin matriz ni marca manda solo el nombre', () => {
    expect(argsSugerencia({ name: 'Gorra' }, MARCAS)).toEqual({
      name: 'Gorra', brand: '', model: '', color: '', size: '',
    })
  })
})

describe('mensajeSugerencia', () => {
  it('avisa cuando el código ya está ocupado', () => {
    const msg = mensajeSugerencia('LV-CHAM', false, '')
    expect(msg).toContain('LV-CHAM')
    expect(msg).toContain('ya lo tiene otra prenda')
  })
  it('avisa que reemplaza lo que el usuario escribió', () => {
    expect(mensajeSugerencia('LV-CHAM', true, 'MIO-1')).toContain('MIO-1')
  })
  it('no habla de reemplazo si el SKU es el mismo o está vacío', () => {
    expect(mensajeSugerencia('LV-CHAM', true, '  ')).not.toContain('Reemplaza')
    expect(mensajeSugerencia('LV-CHAM', true, 'LV-CHAM')).not.toContain('Reemplaza')
  })
})
