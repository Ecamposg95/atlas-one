import { describe, it, expect } from 'vitest'

import { visibleNavItems, type NavItem } from '../navVisibility'

// El Scanner de tienda lo ven los admins de cualquier org con inventario. Para
// una cajera solo debe aparecer cuando la org tiene ADEMÁS el módulo `scanner`
// (lo trae el preset boutique): así el cambio se limita a esas tiendas y las
// cajeras de las demás no ven nada nuevo.

const scanner: NavItem = {
  label: 'Scanner', short: 'SCN', icon: 'fa-barcode', url: '/scanner', group: 'hq', sort: 1,
  module: 'inventory', branchModule: 'scanner',
}
const pos: NavItem = { label: 'POS', short: 'POS', icon: 'fa-cash-register', url: '/pos', group: 'pos', sort: 0 }
const items = [pos, scanner]

const opts = (over: Partial<Parameters<typeof visibleNavItems>[1]>) => ({
  role: 'CAJERO' as const, allowed: ['/pos', '/scanner'], enabledModules: ['inventory'], isGastro: false, ...over,
})

describe('visibleNavItems', () => {
  it('oculta el scanner a la cajera cuando la org no tiene el módulo scanner', () => {
    const urls = visibleNavItems(items, opts({})).map((i) => i.url)
    expect(urls).toEqual(['/pos'])
  })

  it('muestra el scanner a la cajera cuando la org tiene el módulo scanner', () => {
    const urls = visibleNavItems(items, opts({ enabledModules: ['inventory', 'scanner'] })).map((i) => i.url)
    expect(urls).toContain('/scanner')
  })

  it('al admin le basta con inventario, como hasta ahora', () => {
    const urls = visibleNavItems(items, opts({ role: 'ADMINISTRADOR' })).map((i) => i.url)
    expect(urls).toContain('/scanner')
  })

  it('sin scanner en las rutas del rol no aparece aunque el módulo esté', () => {
    const urls = visibleNavItems(items, opts({ allowed: ['/pos'], enabledModules: ['inventory', 'scanner'] })).map((i) => i.url)
    expect(urls).toEqual(['/pos'])
  })

  it('fail-open mientras los módulos no han cargado (lista vacía)', () => {
    const urls = visibleNavItems(items, opts({ enabledModules: [] })).map((i) => i.url)
    expect(urls).toContain('/scanner')
  })

  it('ordena por sort', () => {
    const urls = visibleNavItems([scanner, pos], opts({ role: 'ADMINISTRADOR' })).map((i) => i.url)
    expect(urls).toEqual(['/pos', '/scanner'])
  })
})
