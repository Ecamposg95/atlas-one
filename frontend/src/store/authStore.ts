import { create } from 'zustand'
import type { User, Organization, Branch } from '../types/auth'

interface AuthStore {
  user: User | null
  token: string | null
  org: Organization | null
  branch: Branch | null
  isAuthenticated: boolean
  hydrated: boolean
  // true cuando OTRA pestaña de este equipo inició sesión con un usuario
  // distinto. Es un aviso: el interceptor de `api/client.ts` lee el token de
  // localStorage en cada request, así que a partir de ese momento esta
  // pestaña ya autentica como el otro usuario aunque en pantalla siga el
  // nombre anterior.
  foreignSession: boolean

  setAuth: (user: User, token: string, org: Organization | null) => void
  setBranch: (branch: Branch | null) => void
  logout: () => void
  hydrate: () => void
  dismissForeignSession: () => void
}

// El listener de `storage` se instala una sola vez por pestaña.
let storageListenerReady = false

/**
 * ¿Otra pestaña cambió la sesión bajo nuestros pies?
 *
 * `otroToken` es el valor que quedó en localStorage (lo que escribió la otra
 * pestaña). Es ajeno solo si esta pestaña TIENE sesión y el token difiere. Un
 * `otroToken` nulo es un logout ajeno, no una suplantación: no se avisa.
 */
function esSesionAjena(propio: string | null, otroToken: string | null): boolean {
  if (!propio) return false
  if (!otroToken) return false
  return otroToken !== propio
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  token: null,
  org: null,
  branch: null,
  isAuthenticated: false,
  hydrated: false,
  foreignSession: false,

  setAuth: (user, token, org) => {
    localStorage.setItem('atlas_token', token)
    localStorage.setItem('atlas_user', JSON.stringify(user))
    if (org) {
      localStorage.setItem('atlas_org_id', String(org.id))
      localStorage.setItem('atlas_org', JSON.stringify(org))
    }
    set({ user, token, org, isAuthenticated: true, foreignSession: false })
  },

  setBranch: (branch) => {
    if (branch) {
      localStorage.setItem('atlas_branch', JSON.stringify(branch))
    } else {
      localStorage.removeItem('atlas_branch')
    }
    set({ branch })
  },

  logout: () => {
    localStorage.removeItem('atlas_token')
    localStorage.removeItem('atlas_org_id')
    localStorage.removeItem('atlas_user')
    localStorage.removeItem('atlas_org')
    localStorage.removeItem('atlas_branch')
    set({ user: null, token: null, org: null, branch: null, isAuthenticated: false, foreignSession: false })
  },

  // Restaurar sesión desde localStorage al cargar la app
  hydrate: () => {
    const token = localStorage.getItem('atlas_token')
    const userRaw = localStorage.getItem('atlas_user')
    const orgRaw = localStorage.getItem('atlas_org')
    const branchRaw = localStorage.getItem('atlas_branch')

    if (token && userRaw) {
      try {
        const user = JSON.parse(userRaw) as User
        const org = orgRaw ? (JSON.parse(orgRaw) as Organization) : null
        const branch = branchRaw ? (JSON.parse(branchRaw) as Branch) : null
        set({ user, token, org, branch, isAuthenticated: true, hydrated: true })
      } catch {
        // localStorage corrupto — limpiar
        localStorage.clear()
        set({ hydrated: true })
      }
    } else {
      set({ hydrated: true })
    }

    // Detectar que OTRA pestaña de este equipo cambió la sesión. localStorage
    // es compartido; el evento `storage` solo llega a las OTRAS pestañas, que
    // es justo lo que queremos.
    if (typeof window !== 'undefined' && !storageListenerReady) {
      storageListenerReady = true
      window.addEventListener('storage', (ev) => {
        if (ev.key !== 'atlas_token') return
        if (esSesionAjena(get().token, ev.newValue)) {
          set({ foreignSession: true })
        }
      })
    }
  },

  dismissForeignSession: () => set({ foreignSession: false }),
}))
