/**
 * Colocación del popover de precios del carrito (`PricePickerPopover`).
 *
 * Se extrae del componente para poder probar la aritmética sin navegador: es
 * la que decide si el panel cae arriba o abajo del disparador y —lo que
 * arregla el hallazgo M2 de la auditoría de cajera— cuánto mide de ancho.
 * Con un ancho fijo de 300 px un Android de 360 px dejaba el popover pegado
 * a los bordes; ahora nunca pasa del viewport menos el margen.
 */

/** Lo que se necesita del `DOMRect` del disparador. */
export interface AnclaPopover {
  top: number
  bottom: number
  left: number
}

export interface PosicionPopover {
  top: number
  left: number
  width: number
  /** `below` = debajo del disparador; `above` = encima. */
  placement: 'below' | 'above'
}

/** Ancho deseado del popover. Se recorta si no cabe. */
export const ANCHO_POPOVER = 300
/** Aire mínimo contra cualquier borde del viewport. */
export const MARGEN_POPOVER = 8
/** Separación entre el disparador y el popover. */
const SEPARACION = 4

export function posicionaPopover(
  ancla: AnclaPopover,
  altoPopover: number,
  vw: number,
  vh: number,
  anchoDeseado: number = ANCHO_POPOVER,
  margen: number = MARGEN_POPOVER,
): PosicionPopover {
  const width = Math.max(0, Math.min(anchoDeseado, vw - 2 * margen))

  const espacioAbajo = vh - ancla.bottom - margen
  const cabeAbajo = espacioAbajo >= altoPopover
  const cabeArriba = ancla.top - margen >= altoPopover
  const placement: 'below' | 'above' = cabeAbajo ? 'below' : cabeArriba ? 'above' : 'below'

  const top = placement === 'below'
    ? ancla.bottom + SEPARACION
    : Math.max(margen, ancla.top - altoPopover - SEPARACION)

  let left = ancla.left
  if (left + width > vw - margen) left = vw - width - margen
  if (left < margen) left = margen

  return { top, left, width, placement }
}
