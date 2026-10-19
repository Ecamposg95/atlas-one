import { create } from 'zustand'
import client from '../api/client'
import { puede } from '../utils/capacidades'
import type { PlanOrg } from '../types/auth'
import { leerCamposProducto, TODO_VISIBLE, type CamposProducto } from '../components/products/camposProducto'

/**
 * Apply or clear the `data-preset` attribute on <html>.
 * Drives CSS variable theming defined in src/index.css (per-preset accent
 * colors). No-op when running outside the browser (SSR-safe).
 */
function applyPresetAttribute(preset: string | null) {
  if (typeof document === 'undefined') return
  if (preset) {
    document.documentElement.setAttribute('data-preset', preset)
  } else {
    document.documentElement.removeAttribute('data-preset')
  }
}

interface ContextResponse {
  enabled_modules?: string[]
  preset?: string | null
  capacidades?: string[]
  plan?: { clave?: unknown; nombre?: unknown } | null
  campos_producto?: unknown
  // (other fields present in /me/context but not needed here)
}

/** Solo acepta un plan completo; cualquier otra cosa es "no sé" (null = sin recorte). */
function leerPlan(crudo: ContextResponse['plan']): PlanOrg | null {
  if (!crudo || typeof crudo.clave !== 'string' || typeof crudo.nombre !== 'string') return null
  return { clave: crudo.clave, nombre: crudo.nombre }
}

interface EnabledModulesStore {
  enabledModules: string[]
  preset: string | null
  capacidades: string[]
  /** Plan comercial; null mientras no carga, si falló o si el servidor no lo manda. */
  plan: PlanOrg | null
  /** Campos del formulario de producto según el giro; falla abierto. */
  camposProducto: CamposProducto
  loaded: boolean
  loading: boolean
  load: () => Promise<void>
  reset: () => void
}

/**
 * Cache of enabled modules + active preset for the current user/org.
 * Sourced from GET /api/users/me/context.
 *
 * Use to drive Sidebar gating, dashboard routing, and any UI that
 * depends on which Atlas One modules are active.
 */
export const useEnabledModulesStore = create<EnabledModulesStore>((set, get) => ({
  enabledModules: [],
  preset: null,
  capacidades: [],
  plan: null,
  camposProducto: TODO_VISIBLE,
  loaded: false,
  loading: false,

  load: async () => {
    if (get().loading) return
    set({ loading: true })
    try {
      const r = await client.get<ContextResponse>('/users/me/context')
      const mods = Array.isArray(r.data?.enabled_modules) ? r.data!.enabled_modules! : []
      const preset = r.data?.preset ?? null
      const capacidades = Array.isArray(r.data?.capacidades) ? r.data!.capacidades! : []
      const plan = leerPlan(r.data?.plan)
      set({
        enabledModules: mods,
        preset,
        capacidades,
        plan,
        camposProducto: leerCamposProducto(r.data?.campos_producto),
        loaded: true,
        loading: false,
      })
      applyPresetAttribute(preset)
    } catch {
      // Fail open: if context fetch fails, leave the sidebar showing all
      // items. Better than locking the user out of navigation.
      // Las capacidades NO siguen esta política: fallan cerradas (lista
      // vacía), igual que cuando el servidor sí responde pero la tienda no
      // tiene ninguna encendida.
      set({ enabledModules: [], preset: null, capacidades: [], plan: null, camposProducto: TODO_VISIBLE, loaded: true, loading: false })
      applyPresetAttribute(null)
    }
  },

  reset: () => {
    set({ enabledModules: [], preset: null, capacidades: [], plan: null, camposProducto: TODO_VISIBLE, loaded: false, loading: false })
    applyPresetAttribute(null)
  },
}))

/** `useCapacidad('propina')` — true si la tienda tiene esa función. */
export const useCapacidad = (clave: string): boolean =>
  useEnabledModulesStore((s) => puede(s.capacidades, clave))

/** Campos del formulario de producto que ve este giro. */
export const useCamposProducto = (): CamposProducto =>
  useEnabledModulesStore((s) => s.camposProducto)
