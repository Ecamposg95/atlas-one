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

/**
 * Administrador y dueño no configuran una sucursal sino el negocio:
 * `/configuracion` les abre el centro único de ajustes (empresa, sucursales,
 * ventas y caja, ticket, impresoras…).
 */
export function esCentroDeAjustes(role: Role | null | undefined): boolean {
  return role === 'ADMINISTRADOR' || role === 'DUEÑO'
}

/**
 * Rejilla de las tarjetas de una pestaña de Configuración: una columna, y dos
 * cuando la pantalla es ancha. El corte va en 1400 y no en `xl` (1280) porque
 * el contenido convive con el menú del sistema y la columna de pestañas: a
 * 1280 cada tarjeta quedaría de ~350 px y sus campos en tres columnas no caben.
 * Las tablas y las rejillas de sucursales no la usan: van a todo el ancho.
 */
export const REJILLA_AJUSTES = 'grid grid-cols-1 min-[1400px]:grid-cols-2 gap-4 items-start'
