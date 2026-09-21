import type { Brand, Department, ProductErrors, ProductFormValue, SetField } from './types'

interface Props {
  value: ProductFormValue
  onChange: SetField
  errors: ProductErrors
  departments: Department[]
  brands: Brand[]
}

/** Los cuatro géneros que acepta el backend (`products.gender`). */
export const GENEROS = [
  { value: 'HOMBRE', label: 'Hombre' },
  { value: 'MUJER', label: 'Mujer' },
  { value: 'UNISEX', label: 'Unisex' },
  { value: 'NINO', label: 'Niño' },
]

export function ProductCommercialSection({ value, onChange, errors, departments, brands }: Props) {
  // Vista previa del nombre de venta: la marca primero, el modelo pegado al
  // nombre. Es exactamente lo que va a leer el cajero en el POS y el ticket.
  const marca = brands.find((b) => b.id === value.brand_id)?.name ?? ''
  const prenda = [value.name.trim() || 'Nombre', value.model.trim()].filter(Boolean).join(' ')
  const nombreDeVenta = marca ? `${marca} · ${prenda}` : prenda

  const costOverPrice =
    !errors.cost && Number(value.cost) > 0 && Number(value.price) > 0 && Number(value.cost) > Number(value.price)

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide">Comerciales</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="text-xs text-slate-400 space-y-1">
          Departamento
          <select className="dax-input w-full" value={value.department_id}
            onChange={(e) => onChange('department_id', e.target.value)}>
            <option value="">— Ninguno —</option>
            {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          Marca
          <select className="dax-input w-full" value={value.brand_id}
            onChange={(e) => onChange('brand_id', e.target.value)}>
            <option value="">— Ninguna —</option>
            {brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          Género
          <select className="dax-input w-full" value={value.gender}
            onChange={(e) => onChange('gender', e.target.value)}>
            <option value="">—</option>
            {GENEROS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          Modelo
          <input className="dax-input w-full" value={value.model} placeholder="mezclilla, cargo, slim…"
            onChange={(e) => onChange('model', e.target.value)} />
          <span className="text-slate-600 text-[11px] block">
            Va pegado al nombre: «{nombreDeVenta}».
          </span>
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          Material
          <input className="dax-input w-full" value={value.material} placeholder="Algodón, piel, lana…"
            onChange={(e) => onChange('material', e.target.value)} />
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          Precio *
          <input type="number" step="0.01" min="0" className="dax-input w-full" value={value.price}
            onChange={(e) => onChange('price', e.target.value)} />
          {errors.price && <span className="text-rose-400 text-[11px]">{errors.price}</span>}
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          Costo *
          <input type="number" step="0.01" min="0" className="dax-input w-full" value={value.cost}
            onChange={(e) => onChange('cost', e.target.value)} />
          {errors.cost && <span className="text-rose-400 text-[11px]">{errors.cost}</span>}
          {costOverPrice && (
            <span className="text-amber-400 text-[11px]">Costo mayor al precio — verifica.</span>
          )}
        </label>
        <label className="text-xs text-slate-400 flex items-center gap-2">
          <input type="checkbox" checked={value.has_iva}
            onChange={(e) => onChange('has_iva', e.target.checked)} />
          Aplica IVA
        </label>
        {value.has_iva && (
          <label className="text-xs text-slate-400 space-y-1">
            Tasa IVA (%)
            <input type="number" step="0.01" min="0" className="dax-input w-full" value={value.tax_rate}
              onChange={(e) => onChange('tax_rate', e.target.value)} />
          </label>
        )}
      </div>
    </section>
  )
}
