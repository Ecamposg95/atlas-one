/** Cierra el modal de importación solo si entró algo y no hubo errores por fila. */
export function debeCerrarSolo(r: { created: number; updated: number; errors?: string[] }): boolean {
  return (r.created > 0 || r.updated > 0) && (r.errors?.length ?? 0) === 0
}

/**
 * Qué hace la X o el fondo del importador: tras una carga que creó o actualizó
 * algo hay que recargar la lista (aunque haya errores por fila); si no, solo cerrar.
 */
export function cerrarImportacion(r: { created: number; updated: number } | null): 'recargar' | 'cerrar' {
  return r && (r.created > 0 || r.updated > 0) ? 'recargar' : 'cerrar'
}
