import type { LabelBarcodeElement, LabelTextElement } from '../../api/labels'

/**
 * Geometría de la vista previa: convierte los elementos que devuelve
 * `POST /api/labels/preview` en primitivas de SVG.
 *
 * El lienzo es el de la etiqueta física: 408 × 200 **dots** (51 × 25 mm a 203
 * dpi). No se reescala aquí — el `viewBox` del `<svg>` hace ese trabajo, así
 * que estas funciones trabajan siempre en dots y son independientes del tamaño
 * en pantalla.
 *
 * Sin React ni DOM a propósito: es lo único de la vista previa que se puede
 * probar sin navegador (`svgEtiqueta.test.ts`).
 */

export interface RectBarra {
  x: number
  y: number
  width: number
  height: number
}

/**
 * Barras del código como rectángulos.
 *
 * `bits` es la cadena de módulos ('1' barra, '0' espacio) y cada módulo mide
 * `moduleWidth` dots. Las barras contiguas se funden en UN rectángulo: un
 * EAN-13 son 95 módulos y dibujar 95 `<rect>` de 2 dots deja costuras visibles
 * entre rectángulos adyacentes cuando el navegador antialiasea, además de
 * multiplicar los nodos por nada.
 */
export function barrasDeBits(
  bits: string,
  x: number,
  y: number,
  height: number,
  moduleWidth: number,
): RectBarra[] {
  const ancho = Math.max(1, moduleWidth)
  const rects: RectBarra[] = []
  let inicio = -1
  for (let i = 0; i <= bits.length; i += 1) {
    // Solo '1' es barra; el final de la cadena cierra la racha abierta.
    const esBarra = i < bits.length && bits[i] === '1'
    if (esBarra && inicio === -1) inicio = i
    if (!esBarra && inicio !== -1) {
      rects.push({
        x: x + inicio * ancho,
        y,
        width: (i - inicio) * ancho,
        height,
      })
      inicio = -1
    }
  }
  return rects
}

/** Ancho total que ocupa el código, en dots. */
export function anchoDeBits(bits: string, moduleWidth: number): number {
  return bits.length * Math.max(1, moduleWidth)
}

/**
 * Línea base del texto.
 *
 * En ZPL, `^FO x,y` es la esquina SUPERIOR izquierda de la celda y `height` es
 * el alto de la letra; en SVG, la `y` de un `<text>` es la línea base. El 0.8
 * es la proporción de la altura que queda por encima de la base en una fuente
 * sans escalable (el resto lo ocupan los descendentes).
 */
export function lineaBase(y: number, height: number): number {
  return y + height * 0.8
}

/**
 * Ancla horizontal de un texto.
 *
 * `align: "R"` en el layout significa alineado a la derecha dentro de una caja
 * `^FB` de `width` dots que EMPIEZA en `x` — es el precio. En SVG eso es
 * anclar al borde derecho de esa caja.
 */
export function anclaTexto(el: Pick<LabelTextElement, 'x' | 'width' | 'align'>): {
  x: number
  anchor: 'start' | 'end'
} {
  if (el.align === 'R' && el.width != null) {
    return { x: el.x + el.width, anchor: 'end' }
  }
  return { x: el.x, anchor: 'start' }
}

/**
 * Centro de la línea legible que la Zebra imprime bajo las barras
 * (`^BEN…,Y` / `^BCN…,Y`). Se dibuja centrada bajo el código.
 */
export function centroInterpretacion(el: Pick<LabelBarcodeElement, 'x' | 'bits' | 'module_width'>): number {
  return el.x + anchoDeBits(el.bits, el.module_width) / 2
}
