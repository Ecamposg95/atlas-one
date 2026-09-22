import type { Brand, Department } from '../../types/products'
import { GENEROS } from '../products/ProductCommercialSection'

/**
 * Filtros de la pantalla de etiquetas. Los mismos ejes con los que la tienda
 * piensa el piso: búsqueda libre, departamento, marca, género y existencia.
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
}

export const FILTROS_VACIOS: EstadoFiltros = {
  search: '',
  department_id: '',
  brand_id: '',
  gender: '',
  only_with_stock: false,
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

      <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer sm:col-span-2 lg:col-span-5">
        <input
          type="checkbox"
          className="rounded"
          checked={valor.only_with_stock}
          onChange={(e) => set('only_with_stock', e.target.checked)}
        />
        Solo con existencia
      </label>
    </form>
  )
}
