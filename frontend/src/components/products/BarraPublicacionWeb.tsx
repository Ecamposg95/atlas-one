interface Props {
  seleccionados: number
  ocupado: boolean
  onPublicarSeleccion: () => void
  onQuitarSeleccion: () => void
  onPublicarFiltrado: () => void
  onLimpiar: () => void
}

/** Acciones en bloque del canal «Tienda en línea» sobre el listado de Productos. */
export function BarraPublicacionWeb({ seleccionados, ocupado, onPublicarSeleccion, onQuitarSeleccion, onPublicarFiltrado, onLimpiar }: Props) {
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
      <button type="button" className="dax-btn-secondary text-xs max-sm:min-h-[44px]" disabled={ocupado} onClick={onPublicarFiltrado}>
        Publicar todo lo filtrado
      </button>
    </div>
  )
}
