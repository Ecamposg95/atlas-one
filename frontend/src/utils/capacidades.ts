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

/** Campos del cobro que dependen de una capacidad contratada. */
interface CobroSaneable {
  requires_invoice?: unknown
  tip_amount?: unknown
}

/**
 * Quita del cobro lo que la tienda no contrató.
 *
 * Se aplica en el borde de salida —el payload— y no en cada sitio que escribe el
 * carrito, porque las entradas son varias: un ticket pausado antes del despliegue, una
 * cola sin red con ventas viejas, o una sesión que cambió de organización sin recargar.
 */
export function saneaCobro<T extends CobroSaneable>(
  payload: T,
  puedePropina: boolean,
  puedeFactura: boolean,
): T {
  return {
    ...payload,
    requires_invoice: puedeFactura && payload.requires_invoice === true,
    tip_amount: puedePropina ? Number(payload.tip_amount) || 0 : 0,
  }
}
