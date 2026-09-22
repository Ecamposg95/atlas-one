import type { LabelPreview } from '../../api/labels'
import { anclaTexto, barrasDeBits, centroInterpretacion, lineaBase } from './svgEtiqueta'

/**
 * La etiqueta dibujada a partir de los MISMOS elementos que componen el ZPL
 * (`layout()` en `app/services/labels/zpl.py`). No se reconstruye nada aquí:
 * si la pantalla y el papel discrepan, discrepan en el backend.
 *
 * El `viewBox` es el lienzo en dots (408 × 200 = 51 × 25 mm a 203 dpi) y el
 * ancho lo pone el contenedor, así que la escala es una sola cosa y no hay
 * coordenadas multiplicadas a mano.
 *
 * Los colores son fijos a propósito: esto es PAPEL. Tiene que verse blanco con
 * tinta negra en tema claro y en tema oscuro, porque eso es lo que sale del
 * rollo.
 */

// Pila sans-serif. La Zebra imprime con su fuente escalable A0, que es
// proporcional tipo Helvetica; ninguna fuente del navegador la calca, así que
// la vista previa es fiel en posición y tamaño, aproximada en el trazo.
const FUENTE = 'Helvetica, Arial, "Liberation Sans", sans-serif'

export function EtiquetaSVG({ preview, className = '' }: { preview: LabelPreview; className?: string }) {
  return (
    <svg
      viewBox={`0 0 ${preview.width} ${preview.height}`}
      className={`w-full h-auto rounded-md border border-slate-300 ${className}`}
      style={{ maxWidth: preview.width * 1.15, background: '#ffffff' }}
      role="img"
      aria-label={`Vista previa de la etiqueta ${preview.kind}`}
    >
      <rect x={0} y={0} width={preview.width} height={preview.height} fill="#ffffff" />

      {preview.elements.map((el, i) => {
        if (el.type === 'barcode') {
          return (
            <g key={`b${i}`}>
              {barrasDeBits(el.bits, el.x, el.y, el.height, el.module_width).map((r, j) => (
                <rect key={j} x={r.x} y={r.y} width={r.width} height={r.height} fill="#000000" />
              ))}
              {el.interpretation && (
                <text
                  x={centroInterpretacion(el)}
                  y={el.y + el.height + 18}
                  textAnchor="middle"
                  fontFamily={FUENTE}
                  fontSize={18}
                  fill="#000000"
                >
                  {el.interpretation}
                </text>
              )}
            </g>
          )
        }
        const { x, anchor } = anclaTexto(el)
        return (
          <text
            key={`t${i}`}
            x={x}
            y={lineaBase(el.y, el.height)}
            textAnchor={anchor}
            fontFamily={FUENTE}
            fontSize={el.height}
            fill="#000000"
          >
            {el.text}
          </text>
        )
      })}
    </svg>
  )
}
