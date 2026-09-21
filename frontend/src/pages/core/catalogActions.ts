/**
 * Acciones por producto de `/admin/catalog`.
 *
 * Qué botones aparecen depende del estado del producto (pendiente de
 * aprobación, archivado…). Esa decisión vivía duplicada dentro del JSX de la
 * tabla; al añadir la vista de tarjetas para teléfono habría habido que
 * repetirla, así que se extrae aquí —pura y probable— y las dos vistas la
 * recorren igual.
 */

export type ClaveAccionCatalogo =
  | 'matriz' | 'aprobar' | 'rechazar' | 'historial'
  | 'editar' | 'duplicar' | 'archivar' | 'restaurar'

export interface MetaAccionCatalogo {
  /** Texto del `title` y del `aria-label`; en tarjeta también se pinta. */
  etiqueta: string
  /** Clase de Font Awesome. */
  icono: string
  /** Colores de hover del botón. */
  clase: string
}

export const ACCIONES_CATALOGO: Record<ClaveAccionCatalogo, MetaAccionCatalogo> = {
  matriz:    { etiqueta: 'Matriz de sucursales', icono: 'fa-store',              clase: 'hover:text-indigo-300 hover:bg-indigo-500/10' },
  aprobar:   { etiqueta: 'Aprobar',              icono: 'fa-check',              clase: 'hover:text-emerald-400 hover:bg-emerald-500/10' },
  rechazar:  { etiqueta: 'Rechazar',             icono: 'fa-xmark',              clase: 'hover:text-amber-400 hover:bg-amber-500/10' },
  historial: { etiqueta: 'Historial',            icono: 'fa-clock-rotate-left',  clase: 'hover:text-amber-300 hover:bg-amber-500/10' },
  editar:    { etiqueta: 'Editar',               icono: 'fa-pen-to-square',      clase: 'hover:text-white hover:bg-slate-700' },
  duplicar:  { etiqueta: 'Duplicar',             icono: 'fa-copy',               clase: 'hover:text-cyan-300 hover:bg-cyan-500/10' },
  archivar:  { etiqueta: 'Archivar',             icono: 'fa-box-archive',        clase: 'hover:text-rose-400 hover:bg-rose-500/10' },
  restaurar: { etiqueta: 'Restaurar',            icono: 'fa-box-open',           clase: 'hover:text-emerald-400 hover:bg-emerald-500/10' },
}

/** Producto visto solo por lo que decide sus acciones. */
export interface ProductoAccionable {
  approval_status?: string | null
  is_active?: boolean
}

/**
 * Acciones disponibles para un producto, en el orden en que se pintan.
 *
 * Aprobar y rechazar solo tienen sentido mientras está `PENDING`; archivar y
 * restaurar son excluyentes según `is_active`.
 */
export function accionesDeProducto(p: ProductoAccionable): ClaveAccionCatalogo[] {
  const claves: ClaveAccionCatalogo[] = ['matriz']
  if (p.approval_status === 'PENDING') claves.push('aprobar', 'rechazar')
  claves.push('historial', 'editar', 'duplicar')
  claves.push(p.is_active ? 'archivar' : 'restaurar')
  return claves
}
