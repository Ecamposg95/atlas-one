import type { Branch, BranchActivation, ProductErrors } from './types'

interface Props {
  branches: Branch[]
  activation: Record<number, BranchActivation>
  onToggle: (branchId: number, patch: Partial<BranchActivation>) => void
  onSetAll: (enabled: boolean) => void
  errors: ProductErrors
}

const DEFAULT_ROW: BranchActivation = { enabled: false, is_active_pos: true, is_active_hq: false, is_visible: true }

export function ProductBranchMatrixSection({ branches, activation, onToggle, onSetAll, errors }: Props) {
  const anyNonDefaultFlag = Object.values(activation).some(
    (b) => b.enabled && (!b.is_active_pos || b.is_active_hq || !b.is_visible),
  )

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide">Activación por sucursal</h2>
        <div className="flex gap-2">
          <button type="button" className="dax-btn-secondary text-[11px]" onClick={() => onSetAll(true)}>
            Seleccionar todas
          </button>
          <button type="button" className="dax-btn-secondary text-[11px]" onClick={() => onSetAll(false)}>
            Ninguna
          </button>
        </div>
      </div>
      {errors.target_branch_ids && (
        <div className="text-rose-400 text-[11px]">{errors.target_branch_ids}</div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="text-left py-1">Sucursal</th>
              <th className="py-1">Activar</th>
              <th className="py-1">POS</th>
              <th className="py-1">HQ</th>
              <th className="py-1">Visible</th>
            </tr>
          </thead>
          <tbody>
            {branches.map((b) => {
              const row = activation[b.id] ?? DEFAULT_ROW
              return (
                <tr key={b.id} className="border-t border-slate-800/60">
                  <td className="py-1.5 text-slate-300">
                    {b.name} <span className="text-slate-600">({b.branch_type})</span>
                  </td>
                  <td className="py-1.5">
                    {/* Una casilla de 16 px es un objetivo táctil de 16 px: el
                        `label` la lleva a 44 px sin cambiar su aspecto (M-4). */}
                    <label className="flex min-h-[44px] sm:min-h-0 items-center justify-center cursor-pointer">
                      <input type="checkbox" checked={row.enabled}
                        onChange={(e) => onToggle(b.id, { enabled: e.target.checked })} />
                    </label>
                  </td>
                  <td className="py-1.5">
                    <label className="flex min-h-[44px] sm:min-h-0 items-center justify-center cursor-pointer">
                      <input type="checkbox" disabled={!row.enabled} checked={row.is_active_pos}
                        onChange={(e) => onToggle(b.id, { is_active_pos: e.target.checked })} />
                    </label>
                  </td>
                  <td className="py-1.5">
                    <label className="flex min-h-[44px] sm:min-h-0 items-center justify-center cursor-pointer">
                      <input type="checkbox" disabled={!row.enabled} checked={row.is_active_hq}
                        onChange={(e) => onToggle(b.id, { is_active_hq: e.target.checked })} />
                    </label>
                  </td>
                  <td className="py-1.5">
                    <label className="flex min-h-[44px] sm:min-h-0 items-center justify-center cursor-pointer">
                      <input type="checkbox" disabled={!row.enabled} checked={row.is_visible}
                        onChange={(e) => onToggle(b.id, { is_visible: e.target.checked })} />
                    </label>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {anyNonDefaultFlag && (
        <div className="text-amber-400 text-[11px]">
          Las banderas por sucursal (POS/HQ/Visible) con valores no-default se ajustarán desde la matriz de catálogo después de crear.
        </div>
      )}
    </section>
  )
}
