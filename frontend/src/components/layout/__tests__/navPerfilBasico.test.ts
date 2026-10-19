import { describe, it, expect } from 'vitest'

import { ALL_NAV, ROLE_ROUTES, rolesConAcceso } from '../navConfig'
import { visibleNavItems } from '../navVisibility'
import { OCULTAS_BASICO_HQ, OCULTAS_BASICO_SUCURSAL, recortarPorPerfil, urlsOcultasPorPerfil } from '../navPerfilBasico'
import type { PerfilUi, PlanOrg, Role } from '../../../types/auth'

// Kaory, Coqueta, Imaltzin: preset ATLAS_POS (11 módulos) en plan FREE.
const ATLAS_POS = [
  'core', 'pos', 'cash_management', 'catalog', 'inventory', 'returns',
  'pricing', 'payments', 'reports', 'labels', 'crm',
]
const FREE: PlanOrg = { clave: 'FREE', nombre: 'ONE FREE' }
const ULTRA: PlanOrg = { clave: 'ULTRA_PLUS', nombre: 'ULTRA+' }

const menu = (role: Role, perfilUi: PerfilUi | null | undefined, plan: PlanOrg | null = FREE, enabledModules = ATLAS_POS) =>
  visibleNavItems(ALL_NAV, {
    role, allowed: ROLE_ROUTES[role] ?? [], enabledModules, isGastro: false, plan, perfilUi,
  }).map((i) => i.url)

describe('menú en modo básico', () => {
  it('cajera: exactamente seis entradas (spec §4.1)', () => {
    expect([...menu('CAJERO', 'basico')].sort()).toEqual(
      ['/atlas-pos', '/cash-history', '/pos', '/printer-settings', '/products', '/sales'],
    )
  })

  it('administradora: exactamente ocho entradas (spec §4.2)', () => {
    expect([...menu('ADMINISTRADOR', 'basico')].sort()).toEqual(
      ['/cash-history', '/hq/operations', '/hq/reports-hub', '/organization', '/printer-settings', '/products', '/sales', '/users'],
    )
  })

  it('completo con el mismo plan y módulos: igual que sin perfil (las de paga no notan nada)', () => {
    for (const r of ['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO', 'VENDEDOR'] as Role[]) {
      expect(menu(r, 'completo', ULTRA)).toEqual(menu(r, undefined, ULTRA))
      expect(menu(r, 'completo', FREE)).toEqual(menu(r, null, FREE))
    }
  })

  it('FREE forzada a completo recupera el menú de SP2 (Review Focus #4)', () => {
    const urls = menu('CAJERO', 'completo')
    expect(urls).toContain('/customers')
    expect(urls).toContain('/returns')
    expect(urls).toContain('/labels')
  })

  it('una de paga forzada a básico también se recorta', () => {
    expect(menu('ADMINISTRADOR', 'basico', ULTRA)).not.toContain('/hq/control')
    expect(menu('ADMINISTRADOR', 'basico', ULTRA)).not.toContain('/customers')
  })

  it('una FREE gastro conserva mesas y cocina: la lista esconde, no es blanca', () => {
    const urls = menu('CAJERO', 'basico', FREE, [...ATLAS_POS, 'tables', 'kitchen'])
    expect(urls).toContain('/tables')
    expect(urls).toContain('/kitchen')
  })

  it('esconder no es quitar acceso: rolesConAcceso no depende del perfil', () => {
    expect(rolesConAcceso('/customers')).toContain('CAJERO')
    expect(rolesConAcceso('/hq/control')).toContain('ADMINISTRADOR')
  })

  it('sin perfil o completo no se esconde nada; sucursal y HQ tienen su lista', () => {
    expect(urlsOcultasPorPerfil(null, true)).toEqual([])
    expect(urlsOcultasPorPerfil('completo', false)).toEqual([])
    expect(urlsOcultasPorPerfil('basico', true)).toBe(OCULTAS_BASICO_SUCURSAL)
    expect(urlsOcultasPorPerfil('basico', false)).toBe(OCULTAS_BASICO_HQ)
    const item = ALL_NAV.find((n) => n.url === '/customers')!
    expect(recortarPorPerfil([item], 'basico', true)).toEqual([])
    expect(recortarPorPerfil([item], 'completo', true)).toEqual([item])
  })
})
