/**
 * Ayudas de maquetación para las FILAS REPETIDAS de los formularios
 * (precios escalonados, empaques, variantes…).
 *
 * En escritorio esas filas son una rejilla de columnas fijas y funcionan como
 * una tabla: la etiqueta de cada campo se pinta una sola vez, en la primera
 * fila, y hace de encabezado de columna. En un teléfono la rejilla se apila a
 * una sola columna y ese encabezado deja de existir: de la segunda fila hacia
 * abajo quedarían tres campos sin nombre.
 *
 * `claseEtiquetaFila` resuelve el caso: la etiqueta se pinta SIEMPRE, y de
 * `sm` (640 px) hacia arriba se oculta en todas las filas menos la primera.
 * Así el escritorio se ve exactamente igual que hoy.
 */

/** Estilo de las etiquetas pequeñas de las filas repetidas. */
export const ETIQUETA_FILA_BASE = 'block text-[10px] mb-0.5'

/**
 * Clase de la etiqueta del campo `indice`-ésimo de una lista de filas.
 *
 * @param indice posición de la fila (0 = primera).
 * @param base   clases de estilo de la etiqueta (debe incluir `block`).
 */
export function claseEtiquetaFila(indice: number, base: string = ETIQUETA_FILA_BASE): string {
  return indice === 0 ? base : `${base} sm:hidden`
}
