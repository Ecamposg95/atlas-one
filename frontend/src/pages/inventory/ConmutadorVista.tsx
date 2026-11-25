import type { VistaProductos } from './useVistaProductos'

const OPCIONES: { vista: VistaProductos; icono: string; rotulo: string }[] = [
  { vista: 'tarjetas', icono: 'fa-grip', rotulo: 'Ver en tarjetas' },
  { vista: 'lista', icono: 'fa-list', rotulo: 'Ver en lista' },
]

/** Dos botones solo-icono del kit para alternar entre la rejilla de tarjetas y la lista. */
export function ConmutadorVista({ vista, onCambiar }: { vista: VistaProductos; onCambiar: (v: VistaProductos) => void }) {
  return (
    <div className="flex items-center rounded-full border border-dax-border-dim bg-dax-card p-0.5" role="group" aria-label="Vista">
      {OPCIONES.map((o) => (
        <button
          key={o.vista}
          type="button"
          onClick={() => onCambiar(o.vista)}
          aria-pressed={vista === o.vista}
          className={`dax-btn-icon w-8 h-8 rounded-full flex items-center justify-center transition-colors ${vista === o.vista ? 'bg-dax-accent-soft text-dax-accent-text' : 'text-dax-faint hover:text-dax-text'}`}
          title={o.rotulo}
          aria-label={o.rotulo}
        >
          <i className={`fa-solid ${o.icono} text-xs`} aria-hidden="true" />
        </button>
      ))}
    </div>
  )
}
