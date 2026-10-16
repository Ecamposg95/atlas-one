import type { PlanOrg } from '../../types/auth'

/**
 * En FREE el inicio solo muestra widgets de módulos activos: una tienda que
 * no tiene cotizaciones no necesita una tarjeta que la mande a una pantalla
 * que le dirá "no disponible". El upsell se concentra en UNA tarjeta (la pinta
 * HomeShell), no en cada widget. Fuera de FREE, o sin plan cargado, se ve todo.
 */
export function widgetVisible(
  w: { module?: string },
  plan: PlanOrg | null,
  enabledModules: string[],
): boolean {
  if (!w.module) return true
  if (!plan || plan.clave !== 'FREE') return true
  return enabledModules.includes(w.module)
}

export function separarWidgets<T extends { module?: string }>(
  widgets: T[],
  plan: PlanOrg | null,
  enabledModules: string[],
): { visibles: T[]; ocultos: T[] } {
  const visibles: T[] = []
  const ocultos: T[] = []
  for (const w of widgets) (widgetVisible(w, plan, enabledModules) ? visibles : ocultos).push(w)
  return { visibles, ocultos }
}
