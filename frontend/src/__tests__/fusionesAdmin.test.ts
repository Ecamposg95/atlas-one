import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ALL_NAV, HQ_NAV_GROUPS, ROLE_ROUTES } from '../components/layout/navConfig'
import { OCULTAS_BASICO_HQ } from '../components/layout/navPerfilBasico'

/**
 * Fase 3 del admin (spec 2026-10-23 §4, criterio §8.3): ningún módulo del admin
 * repetido; las URL viejas redirigen conservando la consulta. Si una fusión se
 * deshace o alguien vuelve a enlazar `/hq/sales`, esta guardia lo dice.
 */
const raiz = resolve(__dirname, '..')
const src = (p: string) => readFileSync(resolve(raiz, p), 'utf8')
const FUSIONADAS = ['/hq/sales', '/hq/returns', '/hq/inventory', '/admin/catalog']
const BORRADOS = ['pages/hq/HQSalesLog.tsx', 'pages/hq/HQReturns.tsx', 'pages/hq/HQInventory.tsx', 'pages/core/AdminCatalog.tsx']

describe('Fase 3 del admin: ningún módulo repetido', () => {
  it('las pantallas HQ fusionadas ya no existen', () => {
    for (const f of BORRADOS) expect(existsSync(resolve(raiz, f)), f).toBe(false)
  })

  it('App.tsx redirige las cuatro URL viejas conservando la consulta y no carga los componentes borrados', () => {
    const app = src('App.tsx')
    expect(app).not.toMatch(/HQSalesLog|HQReturns|HQInventory|AdminCatalog/)
    expect(app).toMatch(/path="sales" element=\{<RedirigirConQuery a="\/sales" \/>\}/)
    expect(app).toMatch(/path="returns" element=\{<RedirigirConQuery a="\/returns" \/>\}/)
    expect(app).toMatch(/path="inventory" element=\{<RedirigirConQuery a="\/inventory" \/>\}/)
    expect(app).toMatch(/path="admin\/catalog" element=\{<RedirigirConQuery a="\/products" \/>\}/)
  })

  it('ni el menú, ni los permisos, ni el perfil básico nombran una URL fusionada', () => {
    const urls = ALL_NAV.map((n) => n.url)
    const grupos = HQ_NAV_GROUPS.flatMap((g) => g.urls)
    const permisos = Object.values(ROLE_ROUTES).flat()
    for (const u of FUSIONADAS) {
      expect(urls, u).not.toContain(u)
      expect(grupos, u).not.toContain(u)
      expect(permisos, u).not.toContain(u)
      expect(OCULTAS_BASICO_HQ, u).not.toContain(u)
    }
  })

  it('ninguna pantalla enlaza a una URL fusionada', () => {
    for (const f of ['pages/hq/Inicio.tsx', 'components/layout/Sidebar.tsx', 'pages/menu/MenuVisual.tsx', 'pages/home/PresetHome.tsx']) {
      expect(src(f), f).not.toMatch(/\/hq\/(sales|returns|inventory)|\/admin\/catalog/)
    }
  })
})
