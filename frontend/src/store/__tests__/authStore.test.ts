import { beforeEach, describe, expect, it } from 'vitest'

// El entorno de vitest es `node`: no hay `localStorage`. Se instala uno de
// juguete (mismo patrón que orgPrefs.test.ts) para probar la lógica real de
// escritura/limpieza sin depender del navegador.
const almacen = new Map<string, string>()
;(globalThis as unknown as { localStorage: Storage }).localStorage = {
  getItem: (k: string) => (almacen.has(k) ? almacen.get(k)! : null),
  setItem: (k: string, v: string) => void almacen.set(k, v),
  removeItem: (k: string) => void almacen.delete(k),
  clear: () => almacen.clear(),
  key: (i: number) => [...almacen.keys()][i] ?? null,
  get length() {
    return almacen.size
  },
} as Storage

import { useAuthStore } from '../authStore'
import type { Organization, User } from '../../types/auth'

const usuario = (): User => ({
  id: 1, username: 'ana', email: null, full_name: 'Ana', role: 'CAJERO',
  platform_role: 'NONE', branch_id: 5, organization_id: 5, is_active: true,
})

const org = (): Organization => ({ id: 5, name: 'Novedades Kaory', industry_type: null, hq_branch_id: null })

// Regresión #14: un usuario de tenant (org 5) no cierra sesión; después inicia
// sesión un SUPERADMIN (sin organización). El contexto de la org anterior no
// debe sobrevivir en localStorage, porque el backend confía ciegamente en
// X-Organization-ID para SUPERADMIN sin verificar membresía.
describe('authStore.setAuth', () => {
  beforeEach(() => {
    almacen.clear()
    useAuthStore.setState({ user: null, token: null, org: null, branch: null, isAuthenticated: false })
  })

  it('guarda atlas_org_id/atlas_org cuando el login trae organización', () => {
    useAuthStore.getState().setAuth(usuario(), 'tok-1', org())
    expect(almacen.get('atlas_org_id')).toBe('5')
    expect(almacen.get('atlas_org')).toContain('Novedades Kaory')
  })

  it('limpia atlas_org_id/atlas_org de una sesión previa cuando el login NO trae organización', () => {
    // Sesión anterior (tenant) deja rastro en localStorage.
    useAuthStore.getState().setAuth(usuario(), 'tok-1', org())
    expect(almacen.has('atlas_org_id')).toBe(true)

    // Login de SUPERADMIN: sin organización.
    useAuthStore.getState().setAuth({ ...usuario(), platform_role: 'SUPERADMIN', organization_id: null }, 'tok-2', null)

    expect(almacen.has('atlas_org_id')).toBe(false)
    expect(almacen.has('atlas_org')).toBe(false)
    expect(useAuthStore.getState().org).toBeNull()
  })

  it('setBranch(null) limpia atlas_branch de una sesión previa', () => {
    useAuthStore.getState().setBranch({ id: 20, name: 'Sucursal Roma', branch_type: 'STORE', is_headquarters: false })
    expect(almacen.has('atlas_branch')).toBe(true)

    useAuthStore.getState().setBranch(null)
    expect(almacen.has('atlas_branch')).toBe(false)
    expect(useAuthStore.getState().branch).toBeNull()
  })
})
