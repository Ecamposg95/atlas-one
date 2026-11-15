import { useAuthStore } from '../store/authStore'
import { useEnabledModulesStore } from '../store/enabledModulesStore'

const ROLES_PUBLICAN = new Set(['ADMINISTRADOR', 'DUEÑO'])

/** Canal «Tienda en línea»: `activo` = módulo encendido; `puedePublicar` = activo y admin/dueño. */
export function useCanalTienda(): { activo: boolean; puedePublicar: boolean } {
  const activo = useEnabledModulesStore((s) => s.enabledModules.includes('tienda_en_linea'))
  const role = useAuthStore((s) => s.user?.role)
  return { activo, puedePublicar: activo && !!role && ROLES_PUBLICAN.has(role) }
}
