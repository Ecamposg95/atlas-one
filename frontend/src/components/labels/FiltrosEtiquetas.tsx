import type { Brand, Department } from '../../types/products'
import { haceMinutosLocal, inicioDeHoyLocal } from '../../pages/labels/lote'
import { GENEROS } from '../products/ProductCommercialSection'

/**
 * Filtros de la pantalla de etiquetas. Los mismos ejes con los que la tienda
 * piensa el piso: búsqueda libre, departamento, marca, género, existencia y
 * fecha de alta (para etiquetar el lote recién capturado sin pescar entre el
 * catálogo viejo).
 *
 * Se envían tal cual a `GET /api/labels/candidates`, que es quien decide el
 * alcance real (una cajera solo ve lo de su sucursal).
 */

export interface EstadoFiltros {
  search: string
  department_id: string
  brand_id: string
  gender: string
  only_with_stock: boolean
  /** `YYYY-MM-DDTHH:mm` (o solo fecha) local; vacío = sin filtro. */
  created_after: string
}

export const FILTROS_VACIOS: EstadoFiltros = {
  search: '',
  department_id: '',
  brand_id: '',
  gender: '',
  only_with_stock: false,
  created_after: '',
}

interface Props {
  valor: EstadoFiltros
  onChange: (siguiente: EstadoFiltros) => void
  departamentos: Department[]
  marcas: Brand[]
  /** Se dispara al enviar el formulario (Enter en la búsqueda) o al tocar Buscar. */
  onBuscar: () => void
  cargando: boolean
}

export function FiltrosEtiquetas({ valor, onChange, departamentos, marcas, onBuscar, cargando }: Props) {
  const set = <K extends keyof EstadoFiltros>(k: K, v: EstadoFiltros[K]) => onChange({ ...valor, [k]: v })

  return (
    <form
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end"
      onSubmit={(e) => { e.preventDefault(); onBuscar() }}
    >
      <div className="sm:col-span-2 lg:col-span-2">
        <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
          Buscar
        </label>
        <div className="flex gap-2">
          <input
            className="dax-input w-full text-sm"
            placeholder="SKU, código, nombre…"
            value={valor.search}
            onChange={(e) => set('search', e.target.value)}
          />
          <button type="submit" className="dax-btn-secondary px-3 text-sm whitespace-nowrap" disabled={cargando}>
            <i className={`fa-solid ${cargando ? 'fa-spinner fa-spin' : 'fa-magnifying-glass'}`} />
          </button>
        </div>
      </div>

      <div>
        <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
          Departamento
        </label>
        <select
          className="dax-input w-full text-sm"
          value={valor.department_id}
          onChange={(e) => set('department_id', e.target.value)}
        >
          <option value="">Todos</option>
          {departamentos.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </div>

      <div>
        <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
          Marca
        </label>
        <select
          className="dax-input w-full text-sm"
          value={valor.brand_id}
          onChange={(e) => set('brand_id', e.target.value)}
        >
          <option value="">Todas</option>
          {marcas.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
      </div>

      <div>
        <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
          Género
        </label>
        <select
          className="dax-input w-full text-sm"
          value={valor.gender}
          onChange={(e) => set('gender', e.target.value)}
        >
          <option value="">Todos</option>
          {GENEROS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
        </select>
      </div>

      <div className="sm:col-span-2 lg:col-span-5 flex flex-wrap items-end gap-x-5 gap-y-3">
        <div>
          <label htmlFor="etiquetas-altas-desde"
                 className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
            Altas desde
          </label>
          <div className="flex flex-wrap gap-2">
            <input
              id="etiquetas-altas-desde"
              type="datetime-local"
              className="dax-input text-sm"
              value={valor.created_after}
              onChange={(e) => set('created_after', e.target.value)}
            />
            <button
              type="button"
              className="dax-btn-secondary px-3 text-sm whitespace-nowrap"
              onClick={() => set('created_after', inicioDeHoyLocal())}
              title="Lo dado de alta desde la medianoche"
            >
              Hoy
            </button>
            <button
              type="button"
              className="dax-btn-secondary px-3 text-sm whitespace-nowrap"
              onClick={() => set('created_after', haceMinutosLocal(60))}
              title="Lo dado de alta en los últimos 60 minutos"
            >
              Última hora
            </button>
            {valor.created_after && (
              <button
                type="button"
                className="dax-btn-secondary px-3 text-sm"
                onClick={() => set('created_after', '')}
                aria-label="Quitar el filtro de fecha"
              >
                <i className="fa-solid fa-xmark" />
              </button>
            )}
          </div>
        </div>

        <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer pb-2.5">
          <input
            type="checkbox"
            className="rounded"
            checked={valor.only_with_stock}
            onChange={(e) => set('only_with_stock', e.target.checked)}
          />
          Solo con existencia
        </label>
      </div>
    </form>
  )
}
