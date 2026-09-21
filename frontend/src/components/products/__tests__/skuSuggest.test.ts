import { describe, it, expect } from 'vitest'

import { argsSugerencia, mensajeSugerencia, nombreDeMarca } from '../skuSuggest'
import { buildVariantRows } from '../variantMatrix'

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
  it('manda marca, nombre y modelo, y NUNCA color ni talla', () => {
    // Con matriz de tallas el SKU base es el de la familia: las hermanas le
    // pegan su sufijo (-BEIGE-M). Mandar la primera talla aquí produciría
    // LV-CHAM-MEZ-BEI-CH y hermanas LV-CHAM-MEZ-BEI-CH-BEIGE-M.
    const args = argsSugerencia(
      { name: ' Chamarra ', model: ' mezclilla ', brand_id: 'b1' },
      MARCAS,
    )
    expect(args).toEqual({
      name: 'Chamarra', brand: 'Louis Vuitton', model: 'mezclilla',
      color: '', size: '',
    })
  })
  it('sin marca ni modelo manda solo el nombre', () => {
    expect(argsSugerencia({ name: 'Gorra' }, MARCAS)).toEqual({
      name: 'Gorra', brand: '', model: '', color: '', size: '',
    })
  })
})

describe('el SKU sugerido es el prefijo de la matriz', () => {
  it('las hermanas salen del base con su sufijo, sin repetir la talla', () => {
    const base = 'LV-CHAM-MEZ' // lo que devuelve el endpoint con esos args
    const filas = buildVariantRows(base, ['Beige'], ['CH', 'M', 'G'], [])
    expect(filas.map((f) => f.sku)).toEqual([
      'LV-CHAM-MEZ-BEIGE-CH', 'LV-CHAM-MEZ-BEIGE-M', 'LV-CHAM-MEZ-BEIGE-G',
    ])
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
