import type { ReactNode } from 'react'

/** Columnas de la rejilla: 2 en teléfono hasta 6 en pantallas grandes. */
export const REJILLA_PRODUCTOS = 'grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3'

export interface TarjetaProductoProps {
  nombre: string
  imagen?: string | null
  /** SKU. */
  codigo?: string | null
  /** Código de barras; se pinta solo si es distinto del SKU. */
  codigoBarras?: string | null
  /** Renglón tenue bajo el código (departamento, marca…). */
  detalle?: ReactNode
  precio: ReactNode
  existencia: ReactNode
  /** Distintivo sobre la foto (aprobación, archivado). */
  insignia?: ReactNode
  /** Pie con las acciones que la lista ya ofrece a ese rol; sin él la tarjeta es de consulta. */
  pie?: ReactNode
  /** Abre el detalle al tocar la foto o el nombre. */
  onAbrir?: () => void
}

/**
 * Tarjeta de un producto en la rejilla de `/products`: foto, nombre, código,
 * precio y existencia. A propósito NO recibe el costo: quien la use (cajera,
 * vendedor u oficina) no tiene por dónde pintarlo.
 */
export function TarjetaProducto({ nombre, imagen, codigo, codigoBarras, detalle, precio, existencia, insignia, pie, onAbrir }: TarjetaProductoProps) {
  const barras = codigoBarras && codigoBarras !== codigo ? codigoBarras : null
  const cuerpo = (
    <>
      {/* Caja de proporción fija: con o sin foto la rejilla no brinca. */}
      <span className="relative block w-full aspect-square rounded-2xl bg-dax-elevated overflow-hidden">
        {imagen ? (
          <img src={imagen} alt="" loading="lazy" className="absolute inset-0 w-full h-full object-cover" />
        ) : (
          <span className="absolute inset-0 flex items-center justify-center" data-testid="sin-foto">
            <i className="fa-solid fa-box text-dax-faint text-2xl" aria-hidden="true" />
          </span>
        )}
      </span>
      <span className="block min-w-0 px-1">
        <span className="block text-dax-text text-sm font-medium line-clamp-2 leading-snug">{nombre}</span>
        {(codigo || barras) && (
          <span className="block text-dax-faint text-[11px] font-mono mt-1 truncate">
            {codigo}
            {barras && <span title="Código de barras">{codigo ? ' · ' : ''}{barras}</span>}
          </span>
        )}
        {detalle && <span className="block text-dax-muted text-[11px] mt-0.5 truncate">{detalle}</span>}
      </span>
    </>
  )
  return (
    <article className="dax-card p-3 flex flex-col gap-3 relative min-w-0">
      {onAbrir ? (
        <button type="button" onClick={onAbrir} className="flex flex-col gap-3 w-full min-w-0 text-left">{cuerpo}</button>
      ) : cuerpo}
      <div className="flex items-end justify-between gap-2 px-1 pb-1 mt-auto">
        {precio}
        {existencia}
      </div>
      {pie && <div className="flex items-center gap-2 border-t border-dax-border-dim pt-2">{pie}</div>}
      {insignia && <div className="absolute top-5 left-5 pointer-events-none">{insignia}</div>}
    </article>
  )
}
