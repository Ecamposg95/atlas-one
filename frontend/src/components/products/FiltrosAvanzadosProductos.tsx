import type { Brand } from '../../types/products'
import { GENEROS } from './ProductCommercialSection'
import { AVANZADOS_VACIOS, hayAvanzados, hoyLocal, type FiltrosAvanzados } from './filtrosAvanzadosProductos'

/**
 * Panel plegable «Más filtros» de Productos (`/products`). Se pinta debajo de la
 * barra de filtros solo cuando está abierto (render condicional, nunca `hidden`).
 *
 * Las opciones de talla y color vienen del catálogo de la organización
 * (`GET /api/products/facets`), no de la página cargada: la lista es paginada.
 * La marca se ofrece aquí solo cuando la barra no la trae (fuera del catálogo
 * de HQ en perfil completo): `marcas` en `undefined` = no se pinta.
 */
interface Props {
  id?: string
  valor: FiltrosAvanzados
  onChange: (siguiente: FiltrosAvanzados) => void
  tallas: string[]
  colores: string[]
  /** Mientras llegan las facetas, los selects de talla y color se deshabilitan. */
  cargandoOpciones?: boolean
  marcas?: Brand[]
  marca?: string
  onMarca?: (id: string) => void
}

const ETIQUETA = 'block text-[10px] font-bold uppercase tracking-wider text-dax-muted mb-1'

/** La opción elegida se queda en la lista aunque las facetas aún no lleguen o ya no la traigan. */
function conElegida(opciones: string[], elegida: string): string[] {
  return elegida && !opciones.includes(elegida) ? [elegida, ...opciones] : opciones
}

export function FiltrosAvanzadosProductos({
  id, valor, onChange, tallas, colores, cargandoOpciones = false, marcas, marca = '', onMarca,
}: Props) {
  const set = <K extends keyof FiltrosAvanzados>(k: K, v: FiltrosAvanzados[K]) => onChange({ ...valor, [k]: v })
  const conMarca = marcas !== undefined && onMarca !== undefined

  return (
    <section id={id} className="dax-panel" aria-label="Más filtros">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end">
        <div>
          <label htmlFor="productos-filtro-genero" className={ETIQUETA}>Género</label>
          <select id="productos-filtro-genero" className="dax-input w-full text-sm"
            value={valor.gender} onChange={(e) => set('gender', e.target.value)}>
            <option value="">Todos</option>
            {GENEROS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
          </select>
        </div>

        <div>
          <label htmlFor="productos-filtro-talla" className={ETIQUETA}>Talla</label>
          <select id="productos-filtro-talla" className="dax-input w-full text-sm"
            value={valor.size} disabled={cargandoOpciones && !valor.size}
            onChange={(e) => set('size', e.target.value)}>
            <option value="">{cargandoOpciones ? 'Cargando…' : 'Todas'}</option>
            {conElegida(tallas, valor.size).map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        <div>
          <label htmlFor="productos-filtro-color" className={ETIQUETA}>Color</label>
          <select id="productos-filtro-color" className="dax-input w-full text-sm"
            value={valor.color} disabled={cargandoOpciones && !valor.color}
            onChange={(e) => set('color', e.target.value)}>
            <option value="">{cargandoOpciones ? 'Cargando…' : 'Todos'}</option>
            {conElegida(colores, valor.color).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        {conMarca && (
          <div>
            <label htmlFor="productos-filtro-marca" className={ETIQUETA}>Marca</label>
            <select id="productos-filtro-marca" className="dax-input w-full text-sm"
              value={marca} onChange={(e) => onMarca!(e.target.value)}>
              <option value="">Todas</option>
              {marcas!.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
        )}

        <div>
          <label htmlFor="productos-filtro-alta" className={ETIQUETA}>Dados de alta desde</label>
          <div className="flex gap-2">
            <input id="productos-filtro-alta" type="date" className="dax-input w-full text-sm"
              value={valor.created_after} onChange={(e) => set('created_after', e.target.value)} />
            <button type="button" className="dax-btn-secondary text-xs whitespace-nowrap max-md:min-h-[44px]"
              onClick={() => set('created_after', hoyLocal())} title="Lo dado de alta desde la medianoche">
              Hoy
            </button>
          </div>
        </div>

        <label className="inline-flex items-center gap-2 text-xs text-dax-text select-none py-2 max-md:min-h-[44px]">
          <input type="checkbox" checked={valor.only_with_stock}
            onChange={(e) => set('only_with_stock', e.target.checked)} />
          Solo con existencia
        </label>

        {(hayAvanzados(valor) || (conMarca && marca !== '')) && (
          <div className="sm:col-span-2 lg:col-span-4 flex justify-end">
            <button type="button" className="dax-btn-ghost text-xs max-md:min-h-[44px]"
              onClick={() => { onChange(AVANZADOS_VACIOS); if (conMarca && marca) onMarca!('') }}
              title="Quitar género, talla, color, existencia y fecha">
              <i className="fa-solid fa-filter-circle-xmark" aria-hidden="true" /> Limpiar estos filtros
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
