/**
 * Roles de mostrador: la cajera y el vendedor. Ven solo las ventas de HOY de su
 * sucursal y sin totales del día (el backend lo impone en
 * `app/services/ventas_cajero.py::es_cajero`). El vendedor además no edita el
 * catálogo y su menú es más corto (`ROLE_ROUTES.VENDEDOR`).
 */
export const ROLES_CAJA: readonly string[] = ['CAJERO', 'VENDEDOR']

export function esRolCaja(rol?: string | null): boolean {
  return !!rol && ROLES_CAJA.includes(rol)
}
