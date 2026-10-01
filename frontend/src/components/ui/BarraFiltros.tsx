/**
 * BarraFiltros — fila de filtros de un listado (fechas, buscador, selects y
 * el botón de aplicar/exportar).
 *
 * Escritorio: la misma fila `flex flex-wrap items-end gap-2` de hoy; cada
 * hijo conserva su ancho (`w-36`…). Bajo `sm` (640 px) la regla
 * `.dax-filtros` de `index.css §3` pone cada hijo directo a todo lo ancho y
 * la `accion` a 44 px de alto.
 *
 *   <BarraFiltros accion={<button className="dax-btn-primary">Aplicar</button>}>
 *     <ParFechas>
 *       <input type="date" className="dax-input w-36" … />
 *       <input type="date" className="dax-input w-36" … />
 *     </ParFechas>
 *     <select className="dax-input w-36">…</select>
 *   </BarraFiltros>
 */
import type { ReactNode } from 'react'

export function BarraFiltros({
  children,
  accion,
  className = '',
}: {
  children: ReactNode
  accion?: ReactNode
  className?: string
}) {
  return (
    <div className={`dax-filtros flex flex-wrap items-end gap-2 ${className}`}>
      {children}
      {accion && <div className="dax-filtros-accion">{accion}</div>}
    </div>
  )
}

/**
 * ParFechas — "desde/hasta" juntas en una fila de 2 columnas en teléfono.
 * En `sm` y arriba `sm:contents` disuelve esta envoltura: los dos inputs
 * quedan como hijos directos de la barra, igual que hoy.
 */
export function ParFechas({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`grid grid-cols-2 gap-2 sm:contents ${className}`}>{children}</div>
}

export default BarraFiltros
