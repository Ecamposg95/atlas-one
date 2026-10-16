import type { PlanOrg } from '../../types/auth'
import type { NavItem } from './navVisibility'

/**
 * Perfil por plan: URLs que ese plan NO ve en el menú. Se aplica DESPUÉS del
 * gating por módulo y por rol, y solo esconde: la URL sigue abriendo (el
 * candado real es `require_module` en el backend y `RutaPorRol` en la ruta).
 *
 * FREE (Kaory, Novedades, Coqueta — preset ATLAS_POS): su día es cobrar, corte,
 * ventas, devoluciones, productos, inventario, reportes, impresora, usuarios y
 * sucursal. Lo demás estorba en una PC vieja. Qué se puede esconder se verificó
 * contra producción (plan SP2, Tarea 3) antes de entrar aquí.
 *
 * Un patrón que termina en `/*` esconde por prefijo. Planes que
 * no aparecen = sin recorte.
 */
export const PERFIL_POR_PLAN: Record<string, readonly string[]> = {
  FREE: [
    '/hq/control',
    '/hr/me',
    // Armazón móvil de VENDEDOR/SOPORTE; /mobile/owner (Resumen móvil) se queda: es
    // la vuelta del dueño en teléfono (rutaInicioPorRol).
    '/mobile/dashboard', '/mobile/query', '/mobile/sales', '/mobile/profile',
    '/ai',
    '/quotes', '/quotes/new', '/seguimiento',
  ],
}

export function coincideUrl(url: string, patron: string): boolean {
  if (patron.endsWith('/*')) return url.startsWith(patron.slice(0, -1))
  return url === patron
}

/** Vacío cuando no hay plan (no cargó) o el plan no tiene perfil: fail-open. */
export function urlsOcultasPorPlan(plan: PlanOrg | null | undefined): readonly string[] {
  if (!plan) return []
  return PERFIL_POR_PLAN[plan.clave] ?? []
}

export function recortarPorPlan(items: NavItem[], plan: PlanOrg | null | undefined): NavItem[] {
  const ocultas = urlsOcultasPorPlan(plan)
  if (ocultas.length === 0) return items
  return items.filter((n) => !ocultas.some((p) => coincideUrl(n.url, p)))
}
