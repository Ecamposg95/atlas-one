import { describe, it, expect } from 'vitest'
import { destinoDeRegreso } from '../volver'

describe('destinoDeRegreso', () => {
  it('sin parámetro vuelve al defecto', () => {
    expect(destinoDeRegreso('', '/products')).toBe('/products')
  })
  it('acepta rutas internas', () => {
    expect(destinoDeRegreso('?volver=/admin/catalog', '/products')).toBe('/admin/catalog')
    expect(destinoDeRegreso('?volver=%2Fadmin%2Fcatalog%3Fq%3D1', '/products')).toBe('/admin/catalog?q=1')
  })
  it('rechaza destinos externos o raros', () => {
    expect(destinoDeRegreso('?volver=https://evil', '/products')).toBe('/products')
    expect(destinoDeRegreso('?volver=//evil', '/products')).toBe('/products')
  })
})
