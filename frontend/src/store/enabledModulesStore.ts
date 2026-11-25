import { create } from 'zustand'
import client from '../api/client'
import { puede } from '../utils/capacidades'
import type { PerfilUi, PlanOrg } from '../types/auth'
import { leerCamposProducto, TODO_VISIBLE, type CamposProducto } from '../components/products/camposProducto'
import { leerNoDisponibles, NO_DISPONIBLES, type ModulosNoDisponibles } from '../utils/estadoModulos'

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
  perfil_ui?: unknown
  conteo_ciego?: unknown
  dias_ventas_caja?: unknown
  devolucion_libre_hasta?: unknown
  modulos_no_disponibles?: unknown
  // (other fields present in /me/context but not needed here)
}

/** Solo acepta un plan completo; cualquier otra cosa es "no sé" (null = sin recorte). */
function leerPlan(crudo: ContextResponse['plan']): PlanOrg | null {
  if (!crudo || typeof crudo.clave !== 'string' || typeof crudo.nombre !== 'string') return null
  return { clave: crudo.clave, nombre: crudo.nombre }
}

/** Solo 'basico' acorta la interfaz; ausente (servidor viejo) o raro = completo. */
export function leerPerfilUi(crudo: unknown): PerfilUi {
  return crudo === 'basico' ? 'basico' : 'completo'
}

/** Solo un `false` explícito apaga el conteo ciego; ausente o raro = encendido. */
export function leerConteoCiego(crudo: unknown): boolean {
  return crudo !== false
}

/** Días de ventas pasadas que consulta la caja; ausente o raro = 30 (lo que impone el servidor). */
export function leerDiasVentasCaja(crudo: unknown): number {
  return typeof crudo === 'number' && Number.isFinite(crudo) && crudo >= 0 ? Math.floor(crudo) : 30
}

/** Monto que la caja devuelve sin gerente; ausente o raro = 0 (siempre pide autorización). */
export function leerMontoLibre(crudo: unknown): number {
  const n = typeof crudo === 'string' ? Number(crudo) : crudo
  return typeof n === 'number' && Number.isFinite(n) && n > 0 ? n : 0
}

interface EnabledModulesStore {
  enabledModules: string[]
  preset: string | null
  capacidades: string[]
  /** Plan comercial; null mientras no carga, si falló o si el servidor no lo manda. */
  plan: PlanOrg | null
  /** Campos del formulario de producto según el giro; falla abierto. */
  camposProducto: CamposProducto
  /** Perfil de interfaz; 'completo' mientras no carga, si falló o si el servidor no lo manda. */
  perfilUi: PerfilUi
  /** Conteo ciego del corte; encendido mientras no carga, si falló o si el servidor no lo manda. */
  conteoCiego: boolean
  /** Días hacia atrás que la caja consulta y devuelve ventas (0 = solo hoy). */
  diasVentasCaja: number
  /** Monto hasta el que la caja devuelve sin autorización (0 = nunca). */
  devolucionLibreHasta: number
  /** Módulos sin construir que no se muestran; el espejo local mientras no carga o si el servidor no lo manda. */
  noDisponibles: ModulosNoDisponibles
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
  perfilUi: 'completo',
  conteoCiego: true,
  diasVentasCaja: 30,
  devolucionLibreHasta: 0,
  noDisponibles: NO_DISPONIBLES,
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
        perfilUi: leerPerfilUi(r.data?.perfil_ui),
        conteoCiego: leerConteoCiego(r.data?.conteo_ciego),
        diasVentasCaja: leerDiasVentasCaja(r.data?.dias_ventas_caja),
        devolucionLibreHasta: leerMontoLibre(r.data?.devolucion_libre_hasta),
        noDisponibles: leerNoDisponibles(r.data?.modulos_no_disponibles),
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
      set({ enabledModules: [], preset: null, capacidades: [], plan: null, camposProducto: TODO_VISIBLE, perfilUi: 'completo', conteoCiego: true, diasVentasCaja: 30, devolucionLibreHasta: 0, noDisponibles: NO_DISPONIBLES, loaded: true, loading: false })
      applyPresetAttribute(null)
    }
  },

  reset: () => {
    set({ enabledModules: [], preset: null, capacidades: [], plan: null, camposProducto: TODO_VISIBLE, perfilUi: 'completo', conteoCiego: true, diasVentasCaja: 30, devolucionLibreHasta: 0, noDisponibles: NO_DISPONIBLES, loaded: false, loading: false })
    applyPresetAttribute(null)
  },
}))

/** `useCapacidad('propina')` — true si la tienda tiene esa función. */
export const useCapacidad = (clave: string): boolean =>
  useEnabledModulesStore((s) => puede(s.capacidades, clave))

/** Campos del formulario de producto que ve este giro. */
export const useCamposProducto = (): CamposProducto =>
  useEnabledModulesStore((s) => s.camposProducto)

/** `true` cuando la organización ve la interfaz corta (modo básico). */
export const useModoBasico = (): boolean =>
  useEnabledModulesStore((s) => s.perfilUi === 'basico')

/** Módulos sin construir que la interfaz esconde (`moduloDisponible(clave, mapa)`). */
export const useModulosNoDisponibles = (): ModulosNoDisponibles =>
  useEnabledModulesStore((s) => s.noDisponibles)
