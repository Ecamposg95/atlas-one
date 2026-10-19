// frontend/src/components/layout/navPerfilBasico.ts
import type { PerfilUi } from '../../types/auth'
import type { NavItem } from './navVisibility'
import { coincideUrl } from './navPerfilPlan'

/**
 * Perfil de interfaz "básico" (modo básico, spec 2026-10-18 §4): URLs que NO
 * se ven en el menú. Se aplica DESPUÉS del gating por rol, módulo y plan, y
 * solo esconde: la URL sigue abriendo (`RutaPorRol` no cambia). Es una lista
 * de lo que sobra y no una lista blanca, para que una FREE de otro giro
 * (gastro) conserve sus pantallas.
 *
 * Para esconder algo más en básico, agrégalo aquí (CLAUDE.md §5).
 */

/** Cajera y gerente: Cobrar · Mis ventas · Corte · Productos · Impresora · Mi día. */
export const OCULTAS_BASICO_SUCURSAL: readonly string[] = [
  '/returns',             // se llega desde el ticket en Mis ventas y desde el POS
  '/labels', '/scanner', '/customers', '/hr/me',
  '/reports', '/hq/valor-inventario',   // gerente
]

/** Dueña: Inicio · Mis ventas · Corte · Productos · Reportes · Empresa · Usuarios · Impresora. */
export const OCULTAS_BASICO_HQ: readonly string[] = [
  '/hq/control', '/admin/catalog', '/departments', '/brands', '/labels', '/scanner',
  '/customers', '/hq/branches', '/inventory', '/hq/inventory',
  '/hq/sales', '/hq/returns',          // Mis ventas (/sales) es global para la dueña y devuelve por ticket
  '/hq/valor-inventario',              // entra como tarjeta en el Inicio básico
  '/mobile/owner', '/hr/me', '/ai',
  '/quotes', '/quotes/new', '/seguimiento', '/purchases', '/expenses', '/purchasing',
]

export function urlsOcultasPorPerfil(perfil: PerfilUi | null | undefined, esSucursal: boolean): readonly string[] {
  if (perfil !== 'basico') return []
  return esSucursal ? OCULTAS_BASICO_SUCURSAL : OCULTAS_BASICO_HQ
}

export function recortarPorPerfil(items: NavItem[], perfil: PerfilUi | null | undefined, esSucursal: boolean): NavItem[] {
  const ocultas = urlsOcultasPorPerfil(perfil, esSucursal)
  if (ocultas.length === 0) return items
  return items.filter((n) => !ocultas.some((p) => coincideUrl(n.url, p)))
}
