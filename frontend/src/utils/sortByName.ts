/**
 * Ordena una lista de items con `name` alfabéticamente, en español y sin
 * distinguir mayúsculas/minúsculas ni acentos (p.ej. "Ábaco" antes que
 * "Bolsas"). Usado para poblar selects de marca/departamento en los
 * formularios de producto — defensa en profundidad: el backend ya ordena,
 * pero si algún endpoint no lo hace, el select no debe mostrar orden
 * arbitrario.
 *
 * No muta el arreglo de entrada.
 */
export function sortByName<T extends { name: string }>(items: T[]): T[] {
  return [...items].sort((a, b) =>
    a.name.localeCompare(b.name, 'es', { sensitivity: 'base' })
  )
}
