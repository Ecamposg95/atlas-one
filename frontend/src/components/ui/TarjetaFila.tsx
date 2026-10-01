/**
 * TarjetaFila — la unidad de una lista en teléfono. Reemplaza a un `<tr>`.
 *
 * Bajo `md` (768 px, `useEsTelefono()`) las pantallas de administración
 * dejan de pintar la tabla y pintan una `ListaTarjetas` con una de éstas por
 * fila. Escritorio no la usa: ahí sigue la tabla de siempre.
 *
 *   <TarjetaFila
 *     titulo="A-41"                       // negrita
 *     subtitulo="29/09 14:32 · María"     // una línea, se trunca
 *     importe="$1,250.00"                  // derecha, tabular-nums
 *     estado={<StatusChip … />}           // junto al importe
 *     datos={[{ etiqueta: 'Pago', valor: 'Tarjeta' }]}   // rejilla de 2 columnas
 *     maxDatosVisibles={4}                 // el resto tras "Ver más"
 *     acciones={<>…botones…</>}           // fila al pie, ≥ 44 px de alto
 *     onClick={() => abrirDetalle(v)}      // toda la tarjeta tocable
 *   />
 *
 * Reglas:
 * · Si hay `onClick`, el cuerpo es un `<button>` a todo lo ancho (teclado y
 *   lector de pantalla incluidos). "Ver más" y `acciones` quedan FUERA de ese
 *   botón: un botón no puede contener otro, y un toque en "Reimprimir" no
 *   debe abrir el detalle.
 * · Dentro del `<button>` solo hay `<span>` (contenido de fraseo válido), con
 *   `block`/`grid` para maquetar.
 * · Sin colores nuevos: solo los tokens `--dax-text*` y `--dax-border-dim`.
 * · La raíz lleva `data-tarjeta-fila`: el recorrido de capturas la cuenta.
 */
import { useState, type ReactNode } from 'react'

export interface DatoTarjeta { etiqueta: string; valor: ReactNode }

export interface TarjetaFilaProps {
  titulo: ReactNode
  subtitulo?: ReactNode
  importe?: ReactNode
  estado?: ReactNode
  datos?: DatoTarjeta[]
  /** Cuántos datos se ven sin expandir (default 4). El resto, tras "Ver más". */
  maxDatosVisibles?: number
  acciones?: ReactNode
  onClick?: () => void
  className?: string
  'data-testid'?: string
}

export function TarjetaFila({
  titulo,
  subtitulo,
  importe,
  estado,
  datos = [],
  maxDatosVisibles = 4,
  acciones,
  onClick,
  className = '',
  'data-testid': testId,
}: TarjetaFilaProps) {
  const [expandida, setExpandida] = useState(false)
  const sobran = Math.max(0, datos.length - maxDatosVisibles)
  const visibles = expandida ? datos : datos.slice(0, maxDatosVisibles)

  const contenido = (
    <>
      {/* Cabecera: título/subtítulo a la izquierda; estado + importe a la derecha */}
      <span className="flex items-start justify-between gap-3">
        <span className="block min-w-0">
          <span className="block font-bold text-sm leading-snug truncate" style={{ color: 'var(--dax-text)' }}>
            {titulo}
          </span>
          {subtitulo != null && subtitulo !== '' && (
            <span className="block text-xs truncate mt-0.5" style={{ color: 'var(--dax-text-muted)' }}>
              {subtitulo}
            </span>
          )}
        </span>
        {(estado != null || importe != null) && (
          <span className="flex items-center gap-2 shrink-0">
            {estado}
            {importe != null && (
              <span className="font-semibold text-sm tabular-nums" style={{ color: 'var(--dax-text)' }}>
                {importe}
              </span>
            )}
          </span>
        )}
      </span>

      {visibles.length > 0 && (
        <span className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs mt-2">
          {visibles.map((d, i) => (
            <span key={`${d.etiqueta}-${i}`} className="block min-w-0">
              <span className="block truncate" style={{ color: 'var(--dax-text-faint)' }}>{d.etiqueta}</span>
              <span className="block break-words" style={{ color: 'var(--dax-text)' }}>{d.valor}</span>
            </span>
          ))}
        </span>
      )}
    </>
  )

  return (
    <article data-tarjeta-fila="" data-testid={testId} className={`dax-card p-3 ${className}`}>
      {onClick ? (
        <button
          type="button"
          onClick={onClick}
          className="block w-full text-left rounded-md transition-opacity active:opacity-70"
        >
          {contenido}
        </button>
      ) : (
        <div>{contenido}</div>
      )}

      {sobran > 0 && (
        <button
          type="button"
          aria-expanded={expandida}
          onClick={() => setExpandida(v => !v)}
          className="mt-1 w-full min-h-[44px] flex items-center justify-center gap-1.5 rounded-lg text-xs font-semibold transition-colors hover:bg-black/5 dark:hover:bg-white/10"
          style={{ color: 'var(--dax-text-muted)' }}
        >
          {expandida ? 'Ver menos' : `Ver más (${sobran})`}
          <i className={`fa-solid ${expandida ? 'fa-chevron-up' : 'fa-chevron-down'} text-[10px]`} aria-hidden="true" />
        </button>
      )}

      {acciones != null && (
        <div
          className="flex flex-wrap gap-2 mt-2 pt-2 [&>button]:min-h-[44px] [&>a]:min-h-[44px]"
          style={{ borderTop: '1px solid var(--dax-border-dim)' }}
        >
          {acciones}
        </div>
      )}
    </article>
  )
}

export default TarjetaFila
