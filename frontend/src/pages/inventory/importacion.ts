/** El modal de importación solo se cierra solo cuando no hay nada que leer. */
export function debeCerrarSolo(r: { created: number; updated: number; errors?: string[] }): boolean {
  return (r.created > 0 || r.updated > 0) && (r.errors?.length ?? 0) === 0
}
