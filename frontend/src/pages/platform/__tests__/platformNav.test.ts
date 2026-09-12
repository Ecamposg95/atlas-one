import { describe, it, expect } from 'vitest'
import { NAV_PLATFORM, NAV_ADMIN, MOBILE_PRIMARY_PATHS, splitMobileNav } from '../platformNav'

describe('splitMobileNav (spec §3.2, barra inferior ≤480 px)', () => {
  const all = [...NAV_PLATFORM, ...NAV_ADMIN]

  it('la barra lleva exactamente las 4 rutas primarias, en el orden de MOBILE_PRIMARY_PATHS', () => {
    const { primary } = splitMobileNav(all, MOBILE_PRIMARY_PATHS)
    expect(primary.map((i) => i.to)).toEqual(MOBILE_PRIMARY_PATHS)
    expect(primary).toHaveLength(4)
  })

  it('el resto conserva el orden original y no repite ninguna primaria', () => {
    const { primary, rest } = splitMobileNav(all, MOBILE_PRIMARY_PATHS)
    const primarySet = new Set(primary.map((i) => i.to))
    expect(rest.some((i) => primarySet.has(i.to))).toBe(false)
    expect(rest.length + primary.length).toBe(all.length)
    const restOrder = all.filter((i) => !primarySet.has(i.to)).map((i) => i.to)
    expect(rest.map((i) => i.to)).toEqual(restOrder)
  })

  it('una ruta primaria que no exista en la lista simplemente se omite', () => {
    const { primary } = splitMobileNav(all, ['/platform/metrics', '/platform/no-existe'])
    expect(primary.map((i) => i.to)).toEqual(['/platform/metrics'])
  })

  it('Dashboard, Reportes, Alerts y Cash Audit son las primarias', () => {
    expect(MOBILE_PRIMARY_PATHS).toEqual([
      '/platform/metrics', '/platform/reportes', '/platform/alerts', '/platform/cash-audit',
    ])
  })
})
