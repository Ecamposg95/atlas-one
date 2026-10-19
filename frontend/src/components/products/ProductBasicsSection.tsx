import { campoVisible, TODO_VISIBLE, type CamposProducto } from './camposProducto'
import type { ProductErrors, ProductFormValue, SetField } from './types'

interface Props {
  value: ProductFormValue
  onChange: SetField
  errors: ProductErrors
  /** Pide la sugerencia de SKU. Sin este prop el botón no se pinta. */
  onSuggestSku?: () => void
  suggestingSku?: boolean
  /** Qué campos ve este giro/perfil; sin la prop se ve todo. */
  campos?: CamposProducto
}

const UNIDADES = ['pza', 'kg', 'lt', 'mt', 'caja', 'par', 'srv']

export function ProductBasicsSection({ value, onChange, errors, onSuggestSku, suggestingSku, campos = TODO_VISIBLE }: Props) {
  // 'pza' es el valor por defecto: no cuenta como "ya trae unidad".
  const verUnidad = campoVisible(campos, 'unit', value.unit !== 'pza' ? value.unit : null)
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide">Básicos</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="text-xs text-slate-400 space-y-1">
          Nombre *
          <input className="dax-input w-full" value={value.name}
            onChange={(e) => onChange('name', e.target.value)} />
          {errors.name && <span className="text-rose-400 text-[11px]">{errors.name}</span>}
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          SKU *
          <span className="flex gap-2">
            <input className="dax-input w-full font-mono" value={value.sku}
              onChange={(e) => onChange('sku', e.target.value.toUpperCase().trim())} />
            {onSuggestSku && (
              // La sugerencia NUNCA se aplica sola: el botón pregunta antes de
              // pisar lo que el usuario escribió (ver ProductForm).
              <button type="button" className="dax-btn-secondary text-[11px] whitespace-nowrap"
                onClick={onSuggestSku} disabled={suggestingSku}>
                {suggestingSku
                  ? <i className="fa-solid fa-spinner fa-spin" />
                  : <><i className="fa-solid fa-wand-magic-sparkles mr-1" />Sugerir</>}
              </button>
            )}
          </span>
          {errors.sku && <span className="text-rose-400 text-[11px]">{errors.sku}</span>}
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          Código de barras
          <input className="dax-input w-full font-mono" value={value.barcode}
            onChange={(e) => onChange('barcode', e.target.value)} />
        </label>
        {verUnidad && (
          <label className="text-xs text-slate-400 space-y-1">
            Unidad
            <select className="dax-input w-full" value={value.unit}
              onChange={(e) => onChange('unit', e.target.value)}>
              {UNIDADES.map((u) => <option key={u} value={u}>{u}</option>)}
              {/* Un producto viejo con una unidad fuera de la lista no se queda sin opción. */}
              {value.unit && !UNIDADES.includes(value.unit) && <option value={value.unit}>{value.unit}</option>}
            </select>
          </label>
        )}
        {campoVisible(campos, 'description', value.description) && (
          <label className="text-xs text-slate-400 space-y-1 md:col-span-2">
            Descripción
            <textarea className="dax-input w-full" rows={2} value={value.description}
              onChange={(e) => onChange('description', e.target.value)} />
          </label>
        )}
        {campoVisible(campos, 'image_url', value.image_url) && (
          <label className="text-xs text-slate-400 space-y-1 md:col-span-2">
            URL de imagen
            <input className="dax-input w-full" placeholder="https://..." value={value.image_url}
              onChange={(e) => onChange('image_url', e.target.value)} />
          </label>
        )}
      </div>
    </section>
  )
}
