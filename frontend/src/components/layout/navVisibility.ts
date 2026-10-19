import type { PerfilUi, PlanOrg, Role } from '../../types/auth'
import { recortarPorPlan } from './navPerfilPlan'
import { recortarPorPerfil } from './navPerfilBasico'

/** Roles que operan desde una sucursal (ven BranchNav, no el árbol de HQ). */
export const BRANCH_ROLES: Role[] = ['CAJERO', 'GERENTE']

export interface NavItem {
  label: string; icon: string; url: string; group: string; sort: number; short: string
  /** Optional module gate. If set, the item only appears when the org has
   *  this module enabled (`OrganizationModule.is_enabled=true`). Items without
   *  this field are always visible (subject to ROLE_ROUTES). */
  module?: string
  /** Módulo ADICIONAL que se exige solo a los roles de sucursal (cajero,
   *  gerente). Sirve para abrir una pantalla de HQ a la cajera en ciertas
   *  tiendas sin tocar las demás: p. ej. el Scanner lo ve el admin con
   *  `inventory`, pero la cajera solo si la org además tiene `scanner`
   *  (preset boutique). */
  branchModule?: string
  /** Hide this item for gastro presets (retail-only concept). See GASTRO_PRESETS. */
  hideForGastro?: boolean
}

export interface NavVisibilityOptions {
  role: Role
  /** URLs que ROLE_ROUTES permite a este rol. */
  allowed: string[]
  /** Módulos activos de la org. Vacío = aún no cargó (o falló): fail-open. */
  enabledModules: string[]
  isGastro: boolean
  /** Plan comercial de la org. null/undefined = no cargó: no se recorta (fail-open). */
  plan?: PlanOrg | null
  /** Perfil de interfaz. 'basico' esconde lo de navPerfilBasico; null/undefined/'completo' = nada. */
  perfilUi?: PerfilUi | null
}

/**
 * Decide qué ítems de navegación ve el usuario. Función pura: la barra lateral
 * la llama con el estado de los stores y aquí no hay React ni red.
 *
 * Fail-open: `enabledModules` es vacío solo mientras el contexto no ha cargado
 * (o si la petición falló). En ese estado no se aplica el gating por módulo y
 * se muestra todo lo permitido al rol, antes que dejar al usuario sin menú.
 * Con éxito el backend devuelve al menos ['core'], así que una lista no vacía
 * es autoritativa.
 */
export function visibleNavItems(items: NavItem[], opts: NavVisibilityOptions): NavItem[] {
  const { role, allowed, enabledModules, isGastro, plan, perfilUi } = opts
  const modulesLoaded = enabledModules.length > 0
  const hasModule = (key: string | undefined) => !key || !modulesLoaded || enabledModules.includes(key)
  const isBranchRole = BRANCH_ROLES.includes(role)
  const porModulo = items
    .filter((n) => allowed.includes(n.url))
    .filter((n) => hasModule(n.module))
    .filter((n) => !isBranchRole || hasModule(n.branchModule))
    .filter((n) => !(n.hideForGastro && isGastro))
  // Plan y perfil van al final: solo esconden entre lo que ya pasó rol y módulo.
  const porPlan = recortarPorPlan(porModulo, plan)
  return recortarPorPerfil(porPlan, perfilUi, isBranchRole).sort((a, b) => a.sort - b.sort)
}
