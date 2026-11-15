interface Props {
  seleccionados: number
  ocupado: boolean
  onPublicarSeleccion: () => void
  onQuitarSeleccion: () => void
  onPublicarFiltrado: () => void
  onLimpiar: () => void
  /** false si los filtros en pantalla no caben en el filtro del servidor. */
  filtradoDisponible: boolean
}

/** Acciones en bloque del canal «Tienda en línea» sobre el listado de Productos. */
export function BarraPublicacionWeb({ seleccionados, ocupado, onPublicarSeleccion, onQuitarSeleccion, onPublicarFiltrado, onLimpiar, filtradoDisponible }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Tienda en línea">
      {seleccionados > 0 && (
        <>
          <button type="button" className="dax-btn-primary text-xs max-sm:min-h-[44px]" disabled={ocupado} onClick={onPublicarSeleccion}>
            Publicar en tienda web ({seleccionados})
          </button>
          <button type="button" className="dax-btn-secondary text-xs max-sm:min-h-[44px]" disabled={ocupado} onClick={onQuitarSeleccion}>
            Quitar de tienda web ({seleccionados})
          </button>
          <button type="button" className="dax-btn-ghost text-xs max-sm:min-h-[44px]" onClick={onLimpiar}>Limpiar selección</button>
        </>
      )}
      <button type="button" className="dax-btn-secondary text-xs max-sm:min-h-[44px]" disabled={ocupado || !filtradoDisponible} onClick={onPublicarFiltrado}>
        Publicar todo lo filtrado
      </button>
      {!filtradoDisponible && (
        <span className="text-xs text-dax-muted">
          Quita el filtro de aprobación, «Sin sucursal» o «Incluir archivados» para publicar todo lo filtrado; mientras tanto, selecciona filas.
        </span>
      )}
    </div>
  )
}
