import type { Branch, ProductErrors, ProductFormValue, SetField } from './types'

interface Props {
  value: ProductFormValue
  onChange: SetField
  errors: ProductErrors
  branches: Branch[]
  /**
   * IDs de sucursales en las que el producto queda activado. Para admin: las
   * que marcó en la matriz; para cajero: [user.branch_id] fijo.
   */
  enabledBranchIds: number[]
  /** Si se pasa, oculta el selector y fija el branch destino (modo cajero). */
  lockedBranchId?: number
  /** Copy de footer opcional. */
  footer?: string | null
  /**
   * Con la matriz de variantes activa la existencia se captura por talla
   * (incluida la de la principal, que es este mismo campo). Aquí llega la suma
   * de todas: el número se pinta como resumen y solo queda por elegir la
   * sucursal destino.
   */
  perVariantTotal?: number | null
}

export function ProductInitialStockSection({
  value, onChange, errors, branches, enabledBranchIds, lockedBranchId, footer, perVariantTotal = null,
}: Props) {
  const porVariante = perVariantTotal !== null
  const stockNum = porVariante ? perVariantTotal : Number(value.initial_stock || '0')
  const lockedBranch = lockedBranchId ? branches.find((b) => b.id === lockedBranchId) : null

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide">Inventario inicial (opcional)</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {porVariante ? (
          <div className="text-xs text-slate-400 space-y-1">
            Existencia inicial
            <p className="text-slate-300 font-semibold tabular-nums">{stockNum}</p>
            <p className="text-[11px] text-slate-500">
              Se captura talla por talla en la matriz de arriba.
            </p>
            {errors.initial_stock && <span className="text-rose-400 text-[11px]">{errors.initial_stock}</span>}
          </div>
        ) : (
          <label className="text-xs text-slate-400 space-y-1">
            Stock inicial
            <input type="number" step="0.01" min="0" className="dax-input w-full" value={value.initial_stock}
              onChange={(e) => onChange('initial_stock', e.target.value)} />
            {errors.initial_stock && <span className="text-rose-400 text-[11px]">{errors.initial_stock}</span>}
          </label>
        )}
        {stockNum > 0 && (
          lockedBranch ? (
            <label className="text-xs text-slate-400 space-y-1">
              Sucursal destino
              <input className="dax-input w-full" value={lockedBranch.name} disabled readOnly />
            </label>
          ) : (
            <label className="text-xs text-slate-400 space-y-1">
              Sucursal destino *
              <select className="dax-input w-full" value={value.initial_stock_branch_id}
                onChange={(e) => onChange('initial_stock_branch_id', e.target.value)}>
                <option value="">— Selecciona —</option>
                {enabledBranchIds.map((id) => {
                  const b = branches.find((x) => x.id === id)
                  return b ? <option key={id} value={id}>{b.name}</option> : null
                })}
              </select>
              {errors.initial_stock_branch_id && (
                <span className="text-rose-400 text-[11px]">{errors.initial_stock_branch_id}</span>
              )}
            </label>
          )
        )}
      </div>
      {footer && <p className="text-[11px] text-slate-500">{footer}</p>}
    </section>
  )
}
