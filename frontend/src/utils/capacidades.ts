/**
 * Funciones que la tienda puede usar. El servidor las resuelve en
 * `/users/me/context`; aquí solo se consultan.
 *
 * A diferencia del gateo por módulo del menú, la lista vacía NO significa
 * "todavía no cargó": significa que la tienda no tiene ninguna función apagable
 * encendida, que es una respuesta legítima. Quien necesite distinguir "cargando"
 * usa `loaded` del store.
 */
export function puede(capacidades: string[], clave: string): boolean {
  return capacidades.includes(clave)
}
