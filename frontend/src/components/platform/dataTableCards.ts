import type { DataTableColumn } from './DataTable'

export const CARD_SECONDARY_MAX = 3

/**
 * Partición de columnas para el modo tarjeta de DataTable (≤640 px).
 * La columna `key === 'actions'` (si existe) se separa como `actions` y
 * se excluye de `secondary`, para que no desaparezca en tablas sin
 * `onRowClick` (Organizaciones, Usuarios, API keys).
 */
export function cardColumns<T>(
  columns: DataTableColumn<T>[],
  max: number = CARD_SECONDARY_MAX,
): { primary: DataTableColumn<T>; secondary: DataTableColumn<T>[]; actions: DataTableColumn<T> | undefined } {
  if (columns.length === 0) throw new Error('DataTable sin columnas')
  const primary = columns[0]
  const actions = columns.find((c) => c.key === 'actions')
  const secondary = columns.slice(1).filter((c) => c.key !== 'actions').slice(0, max)
  return { primary, secondary, actions }
}
