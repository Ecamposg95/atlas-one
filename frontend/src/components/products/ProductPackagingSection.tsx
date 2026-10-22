import { emptyPackagingRow, type PackagingRow, type ProductErrors } from './types'

interface Props {
  packagings: PackagingRow[]
  onChange: (rows: PackagingRow[]) => void
  errors?: ProductErrors
}

const MensajeError = ({ texto }: { texto?: string }) => texto ? <span className="text-rose-400 text-[11px] block">{texto}</span> : null

/** Empaques (caja, master…) con su propio código y precio. */
export function ProductPackagingSection({ packagings, onChange, errors = {} }: Props) {
  const actualizar = (i: number, patch: Partial<PackagingRow>) =>
    onChange(packagings.map((u, idx) => (idx === i ? { ...u, ...patch } : u)))
  const quitar = (i: number) => onChange(packagings.filter((_, idx) => idx !== i))

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide">Empaques / Cajas</h2>
        <button type="button" onClick={() => onChange([...packagings, emptyPackagingRow()])}
          className="flex items-center gap-1 text-[10px] font-bold text-indigo-400 hover:text-indigo-300 px-2 py-0.5 rounded hover:bg-indigo-500/10 transition-colors max-md:min-h-[44px]">
          <i className="fa-solid fa-plus" /> Agregar empaque
        </button>
      </div>
      {packagings.length === 0 ? (
        <p className="text-xs py-2 text-center" style={{ color: 'var(--dax-text-faint)' }}>Sin empaques definidos</p>
      ) : (
        <div className="space-y-2">
          {packagings.map((u, i) => (
            <div key={u.id ?? i}
              className="grid grid-cols-1 sm:grid-cols-[1fr_70px_90px_1fr_28px] gap-2 items-end rounded-lg border border-slate-800/70 p-2 sm:rounded-none sm:border-0 sm:p-0">
              <label className="text-[10px] text-slate-500 space-y-0.5">
                Nombre
                <input className="dax-input w-full text-xs" value={u.name} placeholder="Caja"
                  onChange={(e) => actualizar(i, { name: e.target.value })} />
                <MensajeError texto={errors[`packaging.${i}.name`]} />
              </label>
              <label className="text-[10px] text-slate-500 space-y-0.5">
                Unidades
                <input className="dax-input w-full text-xs" type="number" min="1" value={u.units_per_package}
                  onChange={(e) => actualizar(i, { units_per_package: Number(e.target.value) })} />
                <MensajeError texto={errors[`packaging.${i}.units_per_package`]} />
              </label>
              <label className="text-[10px] text-slate-500 space-y-0.5">
                Precio/caja
                <input className="dax-input w-full text-xs" type="number" min="0" step="0.01" value={u.package_price}
                  onChange={(e) => actualizar(i, { package_price: Number(e.target.value) })} />
                <MensajeError texto={errors[`packaging.${i}.package_price`]} />
              </label>
              <label className="text-[10px] text-slate-500 space-y-0.5">
                Código de barras
                <input className="dax-input w-full text-xs font-mono" value={u.barcode} placeholder="Opcional"
                  onChange={(e) => actualizar(i, { barcode: e.target.value })} />
              </label>
              <button type="button" onClick={() => quitar(i)} aria-label={`Quitar el empaque ${i + 1}`}
                className="w-full min-h-[44px] sm:w-7 sm:h-8 sm:min-h-0 flex items-center justify-center gap-1.5 rounded border border-slate-700 sm:border-0 text-slate-500 hover:text-red-400 transition-colors">
                <i className="fa-solid fa-xmark text-xs" />
                <span className="text-[11px] font-semibold sm:hidden">Quitar</span>
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
