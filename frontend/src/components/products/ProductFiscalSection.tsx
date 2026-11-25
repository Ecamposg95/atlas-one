import { campoVisible, TODO_VISIBLE, type CamposProducto } from './camposProducto'
import type { ProductErrors, ProductFormValue, SetField } from './types'

interface Props {
  value: ProductFormValue
  onChange: SetField
  errors: ProductErrors
  campos?: CamposProducto
}

/**
 * Lista corta de claves comunes, solo como sugerencia: el catálogo completo
 * del SAT lo carga Atlas ONE Financials, que es quien valida al facturar.
 * Cualquier otra clave con el formato correcto también se acepta.
 */
export const CLAVES_UNIDAD_COMUNES = [
  { value: 'H87', label: 'H87 · Pieza' },
  { value: 'E48', label: 'E48 · Unidad de servicio' },
  { value: 'ACT', label: 'ACT · Actividad' },
  { value: 'KGM', label: 'KGM · Kilogramo' },
  { value: 'GRM', label: 'GRM · Gramo' },
  { value: 'LTR', label: 'LTR · Litro' },
  { value: 'MLT', label: 'MLT · Mililitro' },
  { value: 'MTR', label: 'MTR · Metro' },
  { value: 'XBX', label: 'XBX · Caja' },
  { value: 'XPK', label: 'XPK · Paquete' },
  { value: 'PR', label: 'PR · Par' },
  { value: 'SET', label: 'SET · Conjunto' },
]

export const CLAVES_PRODUCTO_COMUNES = [
  { value: '01010101', label: 'No existe en el catálogo' },
]

/** c_ObjetoImp del CFDI 4.0, los que usa una tienda. */
export const OBJETOS_IMPUESTO = [
  { value: '02', label: '02 · Sí objeto de impuesto' },
  { value: '01', label: '01 · No objeto de impuesto' },
  { value: '03', label: '03 · Sí objeto, no obligado al desglose' },
]

export const TRATAMIENTOS_IVA = [
  { value: '16', label: 'IVA 16 %' },
  { value: '8', label: 'IVA 8 % (región fronteriza)' },
  { value: '0', label: 'IVA 0 %' },
  { value: 'EXENTO', label: 'Exento de IVA' },
]

const tieneAlgo = (v: ProductFormValue) =>
  [v.sat_clave_prod_serv, v.sat_clave_unidad, v.sat_objeto_imp, v.iva_tratamiento].some((x) => x.trim() !== '')

/**
 * Datos fiscales del producto para facturar. Opcionales: una venta sin ellos
 * se cobra igual; el IVA de la venta se calcula con la tasa de aquí o, si no
 * está, con la tasa general (y queda marcada como deducida).
 */
export function ProductFiscalSection({ value, onChange, errors, campos = TODO_VISIBLE }: Props) {
  if (!campoVisible(campos, 'datos_sat', tieneAlgo(value) ? 'si' : null)) return null
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide">Datos fiscales (SAT)</h2>
      <p className="text-slate-500 text-[11px]">
        Para facturar. Si no los conoces, pídeselos a tu contador; el producto se vende igual sin ellos.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="text-xs text-slate-400 space-y-1">
          Tasa de IVA
          <select className="dax-input w-full" value={value.iva_tratamiento}
            onChange={(e) => onChange('iva_tratamiento', e.target.value)}>
            <option value="">— Sin definir (se usa 16 %) —</option>
            {TRATAMIENTOS_IVA.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          Objeto de impuesto
          <select className="dax-input w-full" value={value.sat_objeto_imp}
            onChange={(e) => onChange('sat_objeto_imp', e.target.value)}>
            <option value="">— Sin definir —</option>
            {OBJETOS_IMPUESTO.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          Clave de producto o servicio
          <input className="dax-input w-full font-mono" inputMode="numeric" maxLength={8}
            list="claves-producto-sat" placeholder="01010101" value={value.sat_clave_prod_serv}
            onChange={(e) => onChange('sat_clave_prod_serv', e.target.value)} />
          <datalist id="claves-producto-sat">
            {CLAVES_PRODUCTO_COMUNES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </datalist>
          {errors.sat_clave_prod_serv && <span className="text-rose-400 text-[11px]">{errors.sat_clave_prod_serv}</span>}
        </label>
        <label className="text-xs text-slate-400 space-y-1">
          Clave de unidad
          <input className="dax-input w-full font-mono" maxLength={3}
            list="claves-unidad-sat" placeholder="H87" value={value.sat_clave_unidad}
            onChange={(e) => onChange('sat_clave_unidad', e.target.value.toUpperCase())} />
          <datalist id="claves-unidad-sat">
            {CLAVES_UNIDAD_COMUNES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </datalist>
          {errors.sat_clave_unidad && <span className="text-rose-400 text-[11px]">{errors.sat_clave_unidad}</span>}
        </label>
      </div>
    </section>
  )
}
