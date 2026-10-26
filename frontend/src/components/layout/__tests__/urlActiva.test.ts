import { describe, it, expect } from 'vitest'
import { urlActiva } from '../navVisibility'

// Menú de oficina tras la Fase 3: /inventory es prefijo de /inventory/conteos
// y /quotes de /quotes/new. Antes del arreglo el sidebar encendía los dos.
const URLS = ['/hq/operations', '/inventory', '/inventory/conteos', '/scanner', '/quotes', '/quotes/new', '/sales']

describe('urlActiva', () => {
  it('en Conteo gana Conteo, no Inventario', () => {
    expect(urlActiva('/inventory/conteos', URLS)).toBe('/inventory/conteos')
  })

  it('dentro de una sesión o su reporte sigue ganando Conteo', () => {
    expect(urlActiva('/inventory/conteos/12', URLS)).toBe('/inventory/conteos')
    expect(urlActiva('/inventory/conteos/12/reporte', URLS)).toBe('/inventory/conteos')
  })

  it('en Inventario y sus subrutas gana Inventario', () => {
    expect(urlActiva('/inventory', URLS)).toBe('/inventory')
    expect(urlActiva('/inventory/42', URLS)).toBe('/inventory')
  })

  it('en Nueva cotización no se enciende Cotizaciones', () => {
    expect(urlActiva('/quotes/new', URLS)).toBe('/quotes/new')
    expect(urlActiva('/quotes', URLS)).toBe('/quotes')
  })

  it('un prefijo sin barra no cuenta como coincidencia', () => {
    expect(urlActiva('/inventory-old', URLS)).toBeNull()
  })

  it('una ruta fuera del menú no enciende nada', () => {
    expect(urlActiva('/pos', URLS)).toBeNull()
    expect(urlActiva('/', URLS)).toBeNull()
  })

  it('no depende del orden de los ítems', () => {
    expect(urlActiva('/inventory/conteos', [...URLS].reverse())).toBe('/inventory/conteos')
  })
})
