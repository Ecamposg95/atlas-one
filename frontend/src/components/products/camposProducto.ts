/**
 * Campos del formulario de producto por giro. El servidor decide
 * (`campos_producto` en /users/me/context); aquí solo se lee y se aplica la
 * regla "nada se apaga": un campo oculto por preset se muestra igual si el
 * producto ya trae valor.
 */
export interface CamposProducto {
  visibles: string[]
  ocultos: string[]
}

export const TODO_VISIBLE: CamposProducto = { visibles: [], ocultos: [] }

export function campoVisible(campos: CamposProducto, clave: string, valorActual?: string | null): boolean {
  if (valorActual != null && String(valorActual).trim() !== '') return true
  return !campos.ocultos.includes(clave)
}

/** Lee lo que mande el servidor; cualquier cosa rara = todo visible. */
export function leerCamposProducto(crudo: unknown): CamposProducto {
  const c = crudo as { visibles?: unknown; ocultos?: unknown } | null | undefined
  if (!c || !Array.isArray(c.visibles) || !Array.isArray(c.ocultos)) return TODO_VISIBLE
  return {
    visibles: c.visibles.filter((x): x is string => typeof x === 'string'),
    ocultos: c.ocultos.filter((x): x is string => typeof x === 'string'),
  }
}
