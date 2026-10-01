/**
 * ListaTarjetas — contenedor de `TarjetaFila` en teléfono.
 *
 * Es el reemplazo de la `<table>` bajo `md`; recibe los mismos textos de
 * vacío/cargando que hoy muestra la tabla de la pantalla. `cargando` gana a
 * `vacio` (mientras carga, la lista suele estar vacía todavía).
 *
 *   <ListaTarjetas cargando={loading} vacio={filas.length === 0} textoVacio="Sin ventas en el periodo">
 *     {filas.map(v => <TarjetaFila key={v.id} … />)}
 *   </ListaTarjetas>
 */
import type { ReactNode } from 'react'
import { Spinner } from './Spinner'

export function ListaTarjetas({
  children,
  vacio,
  textoVacio = 'Sin resultados',
  cargando,
  className = '',
}: {
  children: ReactNode
  vacio?: boolean
  textoVacio?: string
  cargando?: boolean
  className?: string
}) {
  return (
    <div className={`space-y-2 ${className}`} aria-busy={cargando || undefined}>
      {cargando ? (
        <Spinner text="Cargando…" />
      ) : vacio ? (
        <div className="dax-card p-8 text-center text-sm" style={{ color: 'var(--dax-text-muted)' }}>
          {textoVacio}
        </div>
      ) : (
        children
      )}
    </div>
  )
}

export default ListaTarjetas
