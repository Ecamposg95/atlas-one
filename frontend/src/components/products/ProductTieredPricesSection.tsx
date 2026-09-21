import { claseEtiquetaFila } from '../../utils/formResponsivo'
import type { PriceRow, ProductErrors } from './types'
import { emptyPriceRow } from './types'

interface Props {
  prices: PriceRow[]
  onChange: (next: PriceRow[]) => void
  errors?: ProductErrors
  /** Copy de ayuda opcional bajo el header. */
  help?: string
}

export function ProductTieredPricesSection({ prices, onChange, errors, help }: Props) {
  // `errors` se declaraba en Props y no se usaba: los fallos de un renglon
  // quedaban invisibles y el usuario solo veia un aviso generico.
  const errorDe = (i: number, campo: string) => errors?.[`prices.${i}.${campo}`]
  const add = () => onChange([...prices, emptyPriceRow()])
  const remove = (i: number) => onChange(prices.filter((_, idx) => idx !== i))
  const update = (i: number, field: keyof PriceRow, val: string | number) =>
    onChange(prices.map((p, idx) => (idx === i ? { ...p, [field]: val } : p)))

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide">Precios escalonados</h2>
        <button
          type="button"
          onClick={add}
          className="flex items-center gap-1 text-[11px] font-bold text-indigo-400 hover:text-indigo-300 px-2 py-0.5 rounded hover:bg-indigo-500/10 transition-colors min-h-[44px] sm:min-h-0"
        >
          <i className="fa-solid fa-plus" /> Agregar precio
        </button>
      </div>
      {help && <p className="text-[11px] text-slate-500">{help}</p>}

      {prices.length === 0 ? (
        <p className="text-xs py-3 text-center text-slate-500 italic">
          Sin precios adicionales — se usa solo el precio base.
        </p>
      ) : (
        <div className="space-y-2">
          {prices.map((p, i) => (
            // En teléfono la fila se apila a una columna (si no, el campo
            // Nombre queda en 34 px) y cada campo estrena su etiqueta.
            <div
              key={i}
              className="grid grid-cols-1 sm:grid-cols-[1fr_90px_110px_28px] gap-2 items-end rounded-lg border border-slate-800/70 p-2 sm:rounded-none sm:border-0 sm:p-0"
            >
              <div>
                <label className={`${claseEtiquetaFila(i)} text-slate-400`}>Nombre</label>
                <input
                  className="dax-input w-full text-xs"
                  value={p.price_name}
                  onChange={(e) => update(i, 'price_name', e.target.value)}
                  placeholder="ej. Mayoreo"
                />
                {errorDe(i, 'price_name') && (
                  <p className="text-[10px] text-red-400 mt-0.5">{errorDe(i, 'price_name')}</p>
                )}
              </div>
              <div>
                <label className={`${claseEtiquetaFila(i)} text-slate-400`}>Mín. piezas</label>
                <input
                  className="dax-input w-full text-xs"
                  type="number" min="1"
                  value={p.min_quantity}
                  onChange={(e) => update(i, 'min_quantity', Number(e.target.value))}
                />
                {errorDe(i, 'min_quantity') && (
                  <p className="text-[10px] text-red-400 mt-0.5">{errorDe(i, 'min_quantity')}</p>
                )}
              </div>
              <div>
                <label className={`${claseEtiquetaFila(i)} text-slate-400`}>Precio / unidad</label>
                <input
                  className="dax-input w-full text-xs"
                  type="number" min="0" step="0.01"
                  value={p.unit_price}
                  onChange={(e) => update(i, 'unit_price', Number(e.target.value))}
                />
                {errorDe(i, 'unit_price') && (
                  <p className="text-[10px] text-red-400 mt-0.5">{errorDe(i, 'unit_price')}</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => remove(i)}
                className="w-full min-h-[44px] sm:w-7 sm:h-8 sm:min-h-0 flex items-center justify-center gap-1.5 rounded border border-slate-700 sm:border-0 text-slate-500 hover:text-red-400 transition-colors"
                title="Eliminar"
                aria-label={`Eliminar el precio ${i + 1}`}
              >
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
