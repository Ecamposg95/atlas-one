/**
 * CabeceraPagina — título + descripción + acciones de una pantalla.
 *
 * `≥ md`: la fila `flex items-center justify-between flex-wrap gap-3` que hoy
 * cada pantalla arma a mano (escritorio no cambia). `< md`: se apila; la
 * `accionPrincipal` pasa arriba y a todo lo ancho, y las `acciones`
 * secundarias quedan en una fila con `gap-2`.
 *
 *   <CabeceraPagina
 *     titulo={<h1 className="text-2xl font-bold">Ventas</h1>}
 *     acciones={<button className="dax-btn-secondary">Exportar</button>}
 *     accionPrincipal={<button className="dax-btn-primary">Nueva venta</button>}
 *   />
 */
import type { ReactNode } from 'react'

export function CabeceraPagina({
  titulo,
  descripcion,
  acciones,
  accionPrincipal,
  className = '',
}: {
  titulo: ReactNode
  descripcion?: ReactNode
  acciones?: ReactNode
  accionPrincipal?: ReactNode
  className?: string
}) {
  return (
    <div className={`flex flex-col gap-3 md:flex-row md:items-center md:justify-between md:flex-wrap ${className}`}>
      <div className="min-w-0">
        {titulo}
        {typeof descripcion === 'string' ? (
          <p className="text-sm mt-1" style={{ color: 'var(--dax-text-muted)' }}>{descripcion}</p>
        ) : (
          descripcion
        )}
      </div>
      {(acciones || accionPrincipal) && (
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:flex-wrap">
          {acciones && <div className="flex flex-wrap items-center gap-2">{acciones}</div>}
          {accionPrincipal && (
            <div className="order-first md:order-none [&>*]:w-full md:[&>*]:w-auto">{accionPrincipal}</div>
          )}
        </div>
      )}
    </div>
  )
}

export default CabeceraPagina
