import { useAuthStore } from '../store/authStore'
import { useEnabledModulesStore } from '../store/enabledModulesStore'

const ROLES_PUBLICAN = new Set(['ADMINISTRADOR', 'DUEÑO'])

/**
 * Canal «Tienda en línea»: `activo` = módulo encendido; `puedePublicar` = activo
 * y admin/dueño (configuración, reportes, publicar en bloque);
 * `puedePublicarUno` = además el vendedor, que publica producto por producto
 * desde /fotos.
 */
export function useCanalTienda(): { activo: boolean; puedePublicar: boolean; puedePublicarUno: boolean } {
  const activo = useEnabledModulesStore((s) => s.enabledModules.includes('tienda_en_linea'))
  const role = useAuthStore((s) => s.user?.role)
  const puedePublicar = activo && !!role && ROLES_PUBLICAN.has(role)
  return { activo, puedePublicar, puedePublicarUno: puedePublicar || (activo && role === 'VENDEDOR') }
}
