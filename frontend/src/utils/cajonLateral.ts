import type { CSSProperties } from 'react'

/**
 * Cómo se posiciona el sidebar según el ancho. En escritorio no se toca: sigue
 * siendo un hermano en el flujo con sus 244px. Por debajo de 768px se sale de
 * la pantalla y vuelve al abrirse.
 */
export function estiloCajon(esMovil: boolean, abierto: boolean): CSSProperties {
  if (!esMovil) return {}
  return {
    position: 'fixed',
    top: 0,
    left: 0,
    // `dvh` + safe-area: con `100vh` el pie del cajón («Cerrar sesión») queda
    // bajo la barra de URL de iOS, y sin el inset inferior lo tapa la barra de
    // inicio del teléfono.
    height: '100dvh',
    paddingBottom: 'env(safe-area-inset-bottom, 0px)',
    zIndex: 50,
    transform: abierto ? 'translateX(0)' : 'translateX(-100%)',
    transition: 'transform 200ms ease',
  }
}

/**
 * Si el cajón debe quedar fuera del árbol de accesibilidad y del orden de
 * tabulación. `translateX(-100%)` solo lo saca de la vista: un lector de
 * pantalla o un Tab desde el teclado igual lo recorren. Solo aplica cerrado
 * en móvil — en escritorio el sidebar sigue siendo un hermano normal en el
 * flujo, plenamente navegable.
 */
export function cajonEsInerte(esMovil: boolean, abierto: boolean): boolean {
  return esMovil && !abierto
}
