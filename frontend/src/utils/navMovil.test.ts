import { describe, it, expect } from 'vitest'
import { navMovilPorRol } from './navMovil'

describe('navMovilPorRol', () => {
  it('el dueño puede salir del panel hacia el resto de la aplicación', () => {
    // Regresion: "Inicio" apuntaba a '/', que en movil resuelve al propio
    // panel para estos roles. Desde el telefono no quedaba ninguna via hacia
    // el armazon de escritorio, asi que el cajon lateral era inalcanzable
    // justo para el rol al que iba dirigido.
    for (const rol of ['DUEÑO', 'ADMINISTRADOR']) {
      const destinos = navMovilPorRol(rol, 'ATLAS_ONE_RETAIL').map((i) => i.to)
      expect(destinos).toContain('/mobile/owner')
      expect(destinos).toContain('/home')
      expect(destinos).not.toContain('/')
    }
  })

  it('la salida respeta el destino de escritorio de cada preset', () => {
    const destinos = navMovilPorRol('ADMINISTRADOR', 'ATLAS_POS').map((i) => i.to)
    expect(destinos).toContain('/hq/operations')
  })

  it('los demas roles conservan sus pestañas', () => {
    expect(navMovilPorRol('CAJERO').map((i) => i.to)).toEqual([
      '/', '/mobile/comanda', '/mobile/query', '/mobile/profile',
    ])
    expect(navMovilPorRol('VENDEDOR').map((i) => i.to)).toEqual([
      '/mobile/dashboard', '/mobile/sales', '/mobile/query', '/mobile/profile',
    ])
    expect(navMovilPorRol('CLIENTE').map((i) => i.to)).toEqual(['/portal'])
    expect(navMovilPorRol(undefined).map((i) => i.to)).toEqual(['/', '/mobile/profile'])
  })
})


describe('los módulos de la organización mandan sobre la barra', () => {
  it('sin mesas, el cajero ve Vender en vez de Comanda', () => {
    const items = navMovilPorRol('CAJERO', 'ATLAS_POS_BOUTIQUE', ['core', 'pos', 'catalog'])
    expect(items.map((i) => i.label)).toEqual(['Inicio', 'Vender', 'Consultar', 'Perfil'])
    expect(items[1].to).toBe('/pos')
  })
  it('sin mesas, el administrador ve Consultar en vez de Comanda', () => {
    const items = navMovilPorRol('ADMINISTRADOR', 'ATLAS_POS_BOUTIQUE', ['core', 'pos'])
    expect(items.map((i) => i.label)).toEqual(['Resumen', 'Más', 'Consultar', 'Perfil'])
  })
  it('con mesas sigue la comanda', () => {
    expect(navMovilPorRol('CAJERO', 'ATLAS_ONE_RESTAURANT', ['pos', 'tables']).map((i) => i.to)).toContain('/mobile/comanda')
  })
  it('mientras los módulos no cargan no se esconde nada', () => {
    expect(navMovilPorRol('ADMINISTRADOR', 'ATLAS_POS').map((i) => i.to)).toContain('/mobile/comanda')
  })
})
