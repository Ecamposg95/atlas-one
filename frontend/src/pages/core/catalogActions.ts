/**
 * Acciones por producto del catálogo (lista de `/products`, HQ en perfil
 * completo; antes `/admin/catalog`, fusionado en la Fase 3 del admin).
 *
 * Qué botones aparecen depende del estado del producto (pendiente de
 * aprobación, archivado…). La decisión vive aquí —pura y probable— y la tabla
 * (escritorio) y las tarjetas (teléfono) la recorren igual.
 */

export type ClaveAccionCatalogo =
  | 'matriz' | 'aprobar' | 'rechazar' | 'historial'
  | 'editar' | 'duplicar' | 'archivar' | 'restaurar'

/** Clase del botón del kit (botonesDelKit.test.ts): neutras en ghost, aprobar en primary, destructivas en danger. */
export type ClaseBotonAccion = 'dax-btn-ghost' | 'dax-btn-primary' | 'dax-btn-danger'

export interface MetaAccionCatalogo {
  /** Texto del `title` y del `aria-label` («Acción — Producto»); en tarjeta también se pinta. */
  etiqueta: string
  /** Clase de Font Awesome. */
  icono: string
  clase: ClaseBotonAccion
}

export const ACCIONES_CATALOGO: Record<ClaveAccionCatalogo, MetaAccionCatalogo> = {
  matriz:    { etiqueta: 'Matriz de sucursales', icono: 'fa-store',             clase: 'dax-btn-ghost' },
  aprobar:   { etiqueta: 'Aprobar',              icono: 'fa-check',             clase: 'dax-btn-primary' },
  rechazar:  { etiqueta: 'Rechazar',             icono: 'fa-xmark',             clase: 'dax-btn-danger' },
  historial: { etiqueta: 'Historial',            icono: 'fa-clock-rotate-left', clase: 'dax-btn-ghost' },
  editar:    { etiqueta: 'Editar',               icono: 'fa-pencil',            clase: 'dax-btn-ghost' },
  duplicar:  { etiqueta: 'Duplicar',             icono: 'fa-copy',              clase: 'dax-btn-ghost' },
  archivar:  { etiqueta: 'Archivar',             icono: 'fa-box-archive',       clase: 'dax-btn-danger' },
  restaurar: { etiqueta: 'Restaurar',            icono: 'fa-box-open',          clase: 'dax-btn-ghost' },
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
 * restaurar son excluyentes según `is_active`. La matriz va siempre para HQ: archivar
 * apaga el producto en cada sucursal y restaurar no lo reenciende, así que la matriz es la
 * única vía para reactivarlo (el formulario de edición no trae sección de sucursal). La
 * opción `conMatriz: false` queda para quien no deba ofrecerla.
 */
export function accionesDeProducto(p: ProductoAccionable, opciones: { conMatriz?: boolean } = {}): ClaveAccionCatalogo[] {
  const claves: ClaveAccionCatalogo[] = opciones.conMatriz === false ? [] : ['matriz']
  if (p.approval_status === 'PENDING') claves.push('aprobar', 'rechazar')
  claves.push('historial', 'editar', 'duplicar')
  claves.push(p.is_active ? 'archivar' : 'restaurar')
  return claves
}
