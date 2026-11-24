import { moduloDisponible, type ModulosNoDisponibles } from './estadoModulos'

/**
 * ¿Se enseña el botón del agente?
 *
 * Tres condiciones, las mismas del servidor (`app/modules/ai/`):
 *  1. el rol tiene agente (`matriz.py`; superadministrador y soporte, fase A4);
 *  2. la organización tiene encendido el módulo `ai` (`exigir_modulo_ai`);
 *  3. el módulo `ai` está disponible (`estadoModulos`). Hoy está
 *     `en_construccion`, así que el botón NO se ve, igual que el menú.
 *
 * Para verlo antes de destaparlo (desarrollo y pruebas) existe la vista
 * previa, que solo salta la condición 3:
 *  - `VITE_AGENTE_PREVIA=1` al compilar o al correr `npm run dev`, o
 *  - en `npm run dev`, `localStorage.setItem('atlas.agente.previa', '1')`.
 * En un build de producción sin la variable no hay forma de encenderla.
 */
export const ROLES_CON_AGENTE: ReadonlySet<string> = new Set(['CAJERO', 'VENDEDOR', 'GERENTE', 'ADMINISTRADOR', 'DUEÑO'])
export const CLAVE_PREVIA = 'atlas.agente.previa'

export interface EntradaAgenteVisible {
  role: string | null | undefined
  enabledModules: readonly string[]
  noDisponibles: ModulosNoDisponibles
  previa: boolean
}

export function agenteVisible({ role, enabledModules, noDisponibles, previa }: EntradaAgenteVisible): boolean {
  if (!ROLES_CON_AGENTE.has(role ?? '')) return false
  if (!enabledModules.includes('ai')) return false
  return previa || moduloDisponible('ai', noDisponibles)
}

interface EntornoPrevia { DEV?: boolean; VITE_AGENTE_PREVIA?: string }

/** Lee la vista previa del entorno; `entorno` y `almacen` se inyectan en pruebas. */
export function previaDelAgente(
  entorno: EntornoPrevia = import.meta.env as EntornoPrevia,
  almacen: Pick<Storage, 'getItem'> | null = typeof localStorage === 'undefined' ? null : localStorage,
): boolean {
  if (entorno.VITE_AGENTE_PREVIA === '1') return true
  if (!entorno.DEV) return false
  try {
    return almacen?.getItem(CLAVE_PREVIA) === '1'
  } catch {
    return false
  }
}
