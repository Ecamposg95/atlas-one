import type { PlanOrg } from '../../types/auth'

/**
 * El inicio solo muestra widgets de módulos activos, en cualquier plan: una
 * tienda que no tiene Clientes no necesita una tarjeta que mande a su cajera a
 * una pantalla que responde 403 (Kapruy, 2026-11-27; antes solo se recortaba en
 * FREE). El upsell se concentra en UNA tarjeta (la pinta HomeShell), no en cada
 * widget. Sin plan o sin módulos cargados (fail-open) se ve todo.
 */
export function widgetVisible(
  w: { module?: string },
  plan: PlanOrg | null,
  enabledModules: string[],
): boolean {
  if (!w.module) return true
  if (!plan || enabledModules.length === 0) return true
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
