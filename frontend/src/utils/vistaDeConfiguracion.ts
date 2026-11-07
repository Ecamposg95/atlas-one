import type { Role } from '../types/auth'

/**
 * Qué pantalla de Configuración ve cada rol. La caja elige la impresora de su
 * PC, prueba y abre el cajón; la sucursal (papel, ticket, logo, instalación) la
 * configura quien responde por ella: gerente, administrador o dueño.
 */
export type VistaDeConfiguracion = 'caja' | 'completa'

export function vistaDeConfiguracion(role: Role | null | undefined): VistaDeConfiguracion {
  return role === 'ADMINISTRADOR' || role === 'DUEÑO' || role === 'GERENTE' ? 'completa' : 'caja'
}
