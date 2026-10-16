import { describe, it, expect } from 'vitest'

import { ALL_NAV, ROLE_ROUTES, rolesConAcceso } from '../navConfig'
import { visibleNavItems } from '../navVisibility'
import { PERFIL_POR_PLAN, coincideUrl, recortarPorPlan, urlsOcultasPorPlan } from '../navPerfilPlan'
import type { PlanOrg, Role } from '../../../types/auth'

// Kaory, Novedades y Coqueta: preset ATLAS_POS (11 módulos) en plan FREE.
const ATLAS_POS = [
  'core', 'pos', 'cash_management', 'catalog', 'inventory', 'returns',
  'pricing', 'payments', 'reports', 'labels', 'crm',
]
const FREE: PlanOrg = { clave: 'FREE', nombre: 'ONE FREE' }
const ULTRA: PlanOrg = { clave: 'ULTRA_PLUS', nombre: 'ULTRA+' }

const menu = (role: Role, plan: PlanOrg | null, enabledModules = ATLAS_POS) =>
  visibleNavItems(ALL_NAV, {
    role, allowed: ROLE_ROUTES[role] ?? [], enabledModules, isGastro: false, plan,
  }).map((i) => i.url)

// Lo que la dueña y la cajera de una tienda FREE usan a diario: intocable.
const DIARIO_ADMIN = [
  '/hq/operations', '/hq/reports-hub', '/sales', '/products', '/labels', '/printer-settings',
  '/cash-history', '/hq/sales', '/hq/returns', '/hq/inventory', '/admin/catalog',
  '/users', '/hq/branches', '/organization',
]
const DIARIO_CAJERA = [
  '/atlas-pos', '/pos', '/sales', '/cash-history', '/returns', '/products', '/labels', '/printer-settings',
]

describe('perfil FREE', () => {
  it('la administradora conserva toda su operación diaria', () => {
    expect(menu('ADMINISTRADOR', FREE)).toEqual(expect.arrayContaining(DIARIO_ADMIN))
  })

  it('la administradora no ve Control, IA, cotizaciones, Clientes ni el armazón móvil', () => {
    const urls = menu('ADMINISTRADOR', FREE)
    for (const u of ['/hq/control', '/ai', '/quotes', '/quotes/new', '/seguimiento', '/customers', '/mobile/owner']) {
      expect(urls).not.toContain(u)
    }
  })

  it('la cajera conserva Cobrar, Corte, Devoluciones, Productos e Impresora', () => {
    expect(menu('CAJERO', FREE)).toEqual(expect.arrayContaining(DIARIO_CAJERA))
  })

  it('la cajera no ve Mi expediente ni Clientes', () => {
    const urls = menu('CAJERO', FREE)
    expect(urls).not.toContain('/hr/me')
    expect(urls).not.toContain('/customers')
  })

  it('ULTRA+ con los mismos módulos ve todo lo de FREE y además lo recortado', () => {
    const free = menu('ADMINISTRADOR', FREE)
    const ultra = menu('ADMINISTRADOR', ULTRA)
    for (const u of free) expect(ultra).toContain(u)
    expect(ultra).toEqual(expect.arrayContaining(['/hq/control', '/customers', '/mobile/owner']))
    // IA y cotizaciones dependen del módulo, no del plan: sin módulo tampoco en ULTRA+
    expect(ultra).not.toContain('/ai')
    expect(ultra).not.toContain('/quotes')
  })

  it('sin plan (no cargó / servidor viejo) no se recorta nada', () => {
    expect(menu('ADMINISTRADOR', null)).toContain('/hq/control')
    expect(menu('ADMINISTRADOR', null)).toContain('/customers')
  })

  it('plan desconocido = sin recorte, sin excepción', () => {
    expect(menu('ADMINISTRADOR', { clave: 'XYZ', nombre: '?' })).toEqual(menu('ADMINISTRADOR', null))
  })

  it('esconder no quita acceso: el guard de ruta no depende del plan', () => {
    expect(rolesConAcceso('/hq/control')).toContain('ADMINISTRADOR')
    expect(rolesConAcceso('/hr/me')).toContain('CAJERO')
  })

  it('toda URL del perfil apunta a un ítem real (sin fantasmas)', () => {
    const urls = ALL_NAV.map((i) => i.url)
    for (const patron of PERFIL_POR_PLAN.FREE) {
      expect(urls.some((u) => coincideUrl(u, patron)), patron).toBe(true)
    }
  })
})

describe('coincideUrl', () => {
  it('iguala exacto o por prefijo con /*', () => {
    expect(coincideUrl('/hr/me', '/hr/me')).toBe(true)
    expect(coincideUrl('/hr', '/hr/me')).toBe(false)
    expect(coincideUrl('/mobile/owner', '/mobile/*')).toBe(true)
    expect(coincideUrl('/mobile', '/mobile/*')).toBe(false)
    expect(coincideUrl('/mobiles/x', '/mobile/*')).toBe(false)
  })
})

describe('recortarPorPlan', () => {
  it('devuelve la misma lista (misma referencia) cuando no hay nada que recortar', () => {
    const items = ALL_NAV.slice(0, 3)
    expect(recortarPorPlan(items, null)).toBe(items)
    expect(recortarPorPlan(items, ULTRA)).toBe(items)
  })

  it('no reordena lo que deja', () => {
    const urls = recortarPorPlan(ALL_NAV, FREE).map((i) => i.url)
    const esperado = ALL_NAV.map((i) => i.url).filter((u) => !urlsOcultasPorPlan(FREE).some((p) => coincideUrl(u, p)))
    expect(urls).toEqual(esperado)
  })
})
