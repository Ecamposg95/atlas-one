import type { PerfilUi } from '../../types/auth'

/**
 * Qué controles opcionales pinta el POS según el perfil de interfaz (modo
 * básico, spec 2026-10-18 §4.1). Solo decide qué se MUESTRA: el cobro
 * (`saneaCobro`, propina y factura por capacidad, comisión de tarjeta) no
 * cambia. Un dato que ya viene en el ticket (un descuento o un cliente de un
 * ticket pausado) se sigue viendo aunque su control esté escondido.
 */
export interface OpcionesPos {
  /** Descuento por renglón y descuento global. */
  descuentos: boolean
  /** Botón «Cliente» del carrito. */
  cliente: boolean
  /** Equivalente en dólares (bajo el total y en las tarjetas del buscador). */
  usd: boolean
  /** Editar el producto desde el carrito o desde «Ver detalles» del buscador. */
  editarProducto: boolean
  /** Forzar el precio por pieza al vender por caja. */
  forzarPieza: boolean
  /** Alta rápida con el formulario corto en vez de la ficha completa. */
  altaCorta: boolean
}

const COMPLETO: OpcionesPos = {
  descuentos: true, cliente: true, usd: true, editarProducto: true, forzarPieza: true, altaCorta: false,
}
const BASICO: OpcionesPos = {
  descuentos: false, cliente: false, usd: false, editarProducto: false, forzarPieza: false, altaCorta: true,
}

/** Sin perfil (el contexto no ha cargado) = completo: nunca un básico a medias para una de paga. */
export function opcionesPorPerfil(perfil: PerfilUi | null | undefined): OpcionesPos {
  return { ...(perfil === 'basico' ? BASICO : COMPLETO) }
}
