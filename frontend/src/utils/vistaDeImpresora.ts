import type { Role } from '../types/auth'

/**
 * Qué pantalla de impresora ve cada rol. La cajera solo elige la impresora de
 * su PC y prueba; la sucursal (ancho de papel, ticket, logo, instalación) la
 * configura el administrador o el dueño en la pantalla completa.
 */
export type VistaDeImpresora = 'cajera' | 'admin'

export function vistaDeImpresora(role: Role | null | undefined): VistaDeImpresora {
  return role === 'ADMINISTRADOR' || role === 'DUEÑO' ? 'admin' : 'cajera'
}
