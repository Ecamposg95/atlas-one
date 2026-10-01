/**
 * CabeceraPagina — título + descripción + acciones de una pantalla.
 *
 * `≥ md`: la fila `flex items-center justify-between flex-wrap gap-3` que hoy
 * cada pantalla arma a mano (escritorio no cambia). `< md`: se apila; la
 * `accionPrincipal` pasa arriba y a todo lo ancho, y las `acciones`
 * secundarias quedan en una fila con `gap-2`. Bajo md cada acción (primaria y
 * secundarias) tiene un piso de 44 px de alto; en escritorio no se toca nada
 * (solo hay utilidades `max-md:`).
 *
 * Si una secundaria debe quedar en solo icono en teléfono, eso lo hace la
 * pantalla que llama: botón con `dax-btn-icon` + `aria-label` (el componente
 * recibe nodos arbitrarios y no los transforma).
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
          {acciones && <div className="flex flex-wrap items-center gap-2 max-md:[&>*]:min-h-[44px]">{acciones}</div>}
          {accionPrincipal && (
            <div className="order-first md:order-none max-md:[&>*]:w-full max-md:[&>*]:min-h-[44px]">{accionPrincipal}</div>
          )}
        </div>
      )}
    </div>
  )
}

export default CabeceraPagina
