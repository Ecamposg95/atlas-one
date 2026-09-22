import { describe, it, expect } from 'vitest'

import {
  ALL_NAV, ROLE_ROUTES, HQ_NAV_GROUPS, BRANCH_NAV_GROUPS,
  ROUTE_TITLES, routeTitle, rolesConAcceso,
} from '../navConfig'
import { visibleNavItems } from '../navVisibility'
import type { Role } from '../../../types/auth'

/** Menú tal como lo vería alguien de esta organización. */
const menu = (role: Role, enabledModules: string[], isGastro = false) =>
  visibleNavItems(ALL_NAV, {
    role, allowed: ROLE_ROUTES[role] ?? [], enabledModules, isGastro,
  }).map((i) => i.url)

// Eleven Fashion: boutique de una sola sucursal, preset ATLAS_POS_BOUTIQUE.
const BOUTIQUE = [
  'core', 'pos', 'cash_management', 'catalog', 'inventory', 'returns',
  'pricing', 'payments', 'reports', 'scanner', 'variants', 'labels',
]

describe('el menú de la boutique', () => {
  it('le da a la administradora camino para cobrar, reimprimir, etiquetar y configurar la impresora', () => {
    const urls = menu('ADMINISTRADOR', BOUTIQUE)
    expect(urls).toEqual(expect.arrayContaining([
      '/pos', '/sales', '/products', '/labels', '/printer-settings',
    ]))
  })

  it('no muestra Compras, Gastos ni Recursos Humanos: la boutique no tiene esos módulos', () => {
    const urls = menu('ADMINISTRADOR', BOUTIQUE)
    expect(urls).not.toContain('/purchases')
    expect(urls).not.toContain('/expenses')
    expect(urls).not.toContain('/hr')
  })

  it('sí los muestra donde el preset los incluye', () => {
    const urls = menu('ADMINISTRADOR', [...BOUTIQUE, 'purchasing', 'finance', 'hr'])
    expect(urls).toEqual(expect.arrayContaining(['/purchases', '/expenses', '/hr']))
  })

  it('mantiene el fail-open mientras los módulos no cargan', () => {
    expect(menu('ADMINISTRADOR', [])).toContain('/purchases')
  })
})

describe('los grupos del menú', () => {
  it('«Mi tienda» reúne el trabajo diario de la tienda', () => {
    const grupo = HQ_NAV_GROUPS.find((g) => g.header === 'Mi tienda')
    expect(grupo?.urls).toEqual(['/pos', '/sales', '/products', '/labels', '/printer-settings'])
  })

  it('el corte de caja tiene grupo propio y ya no cae en «Más»', () => {
    const grupo = HQ_NAV_GROUPS.find((g) => g.urls.includes('/cash-history'))
    expect(grupo?.header).toBe('Caja')
  })

  it('ninguna URL está en dos grupos (se pintaría dos veces)', () => {
    for (const grupos of [HQ_NAV_GROUPS, BRANCH_NAV_GROUPS]) {
      const urls = grupos.flatMap((g) => g.urls)
      expect(new Set(urls).size).toBe(urls.length)
    }
  })

  it('el ítem del corte de caja se llama «Corte de caja»', () => {
    expect(ALL_NAV.find((n) => n.url === '/cash-history')?.label).toBe('Corte de caja')
  })
})

describe('los rótulos', () => {
  it('no dicen «HQ» ni «Global»', () => {
    const sospechosos = ALL_NAV.filter((n) => /\bHQ\b|Global/i.test(n.label))
    expect(sospechosos.map((n) => n.label)).toEqual([])
  })
})

describe('el título de la barra superior', () => {
  it('sale del mismo NavItem que el menú, no de una segunda lista', () => {
    for (const item of ALL_NAV) {
      expect(ROUTE_TITLES[item.url]).toBe(item.label)
    }
  })

  it('usa el rótulo del menú para las pantallas que antes tenían dos nombres', () => {
    expect(routeTitle('/hq/inventory')).toBe('Existencias')
    expect(routeTitle('/products')).toBe('Productos')
    expect(routeTitle('/cash-history')).toBe('Corte de caja')
    expect(routeTitle('/printer-settings')).toBe('Impresora')
  })

  it('cae al ítem más específico del que cuelga la URL', () => {
    expect(routeTitle('/products/42/edit')).toBe('Productos')
    expect(routeTitle('/hq/branches/3')).toBe('Sucursales')
  })

  it('prefiere el prefijo más largo cuando hay dos candidatos', () => {
    expect(routeTitle('/mobile/comanda/7')).toBe('Comanda')
  })

  it('no deja pantallas sin nombre', () => {
    expect(routeTitle('/ruta/que/no/existe')).toBe('Atlas One')
  })
})

describe('las guardas de ruta', () => {
  it('se derivan de la misma lista que dibuja el menú', () => {
    expect(rolesConAcceso('/users')).toContain('ADMINISTRADOR')
    expect(rolesConAcceso('/pos')).toContain('CAJERO')
  })

  it('dejan fuera a la cajera de Usuarios y de Empresa', () => {
    expect(rolesConAcceso('/users')).not.toContain('CAJERO')
    expect(rolesConAcceso('/organization')).not.toContain('CAJERO')
    expect(rolesConAcceso('/hq/operations')).not.toContain('CAJERO')
  })

  it('el dueño hereda lo del administrador aunque su menú sea más corto', () => {
    expect(rolesConAcceso('/users')).toContain('DUEÑO')
    expect(ROLE_ROUTES.DUEÑO).not.toContain('/users')
  })

  it('una ruta de nadie no se la queda nadie', () => {
    expect(rolesConAcceso('/ruta/inventada')).toEqual([])
  })
})
