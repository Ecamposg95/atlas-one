import { useEffect, useState } from 'react'

import { buildVariantRows, parseList, type VariantRow } from './variantMatrix'

interface Props {
  baseSku: string
  rows: VariantRow[]
  onRowsChange: (rows: VariantRow[]) => void
}

/**
 * Matriz color × talla (preset boutique). El admin escribe los colores y las
 * tallas separados por coma; cada combinación es una variante con su SKU
 * sugerido, su código de barras y (opcional) su precio. La variante principal
 * (SKU base) no aparece aquí: es la que capturan los campos de arriba.
 */
export function ProductVariantsSection({ baseSku, rows, onRowsChange }: Props) {
  const [colors, setColors] = useState('')
  const [sizes, setSizes] = useState('')

  const regenerate = (c: string, s: string) => {
    onRowsChange(buildVariantRows(baseSku, parseList(c), parseList(s), rows))
  }
  const setRow = (key: string, patch: Partial<VariantRow>) => {
    onRowsChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  }

  // El SKU sugerido de cada fila se compone con el SKU base; si el admin lo
  // edita después de escribir colores/tallas, las filas quedaban con el
  // prefijo viejo. Regenerar solo cuando ya hay filas evita crear filas de la
  // nada a partir de un baseSku vacío.
  useEffect(() => {
    if (rows.length > 0) regenerate(colors, sizes)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseSku])

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-black uppercase tracking-wide text-slate-300">Variantes (color / talla)</h3>
      <p className="text-[11px] text-slate-500">
        Escribe colores y tallas separados por coma. Cada combinación se crea como una variante con su
        propio código y existencia. Si la prenda no tiene variantes, deja esto vacío.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="text-xs text-slate-400">Colores</span>
          <input className="dax-input mt-1" value={colors} placeholder="Rojo, Negro, Azul marino"
                 onChange={(e) => { setColors(e.target.value); regenerate(e.target.value, sizes) }} />
        </label>
        <label className="block">
          <span className="text-xs text-slate-400">Tallas</span>
          <input className="dax-input mt-1" value={sizes} placeholder="S, M, L, XL"
                 onChange={(e) => { setSizes(e.target.value); regenerate(colors, e.target.value) }} />
        </label>
      </div>
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-400">
                <th className="py-1 pr-2">Variante</th>
                <th className="py-1 pr-2">SKU</th>
                <th className="py-1 pr-2">Código de barras</th>
                <th className="py-1 pr-2">Precio (vacío = base)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td className="py-1 pr-2 font-semibold text-slate-200">{[r.color, r.size].filter(Boolean).join(' / ')}</td>
                  <td className="py-1 pr-2"><input className="dax-input" value={r.sku} onChange={(e) => setRow(r.key, { sku: e.target.value })} /></td>
                  <td className="py-1 pr-2"><input className="dax-input" value={r.barcode} inputMode="numeric" onChange={(e) => setRow(r.key, { barcode: e.target.value })} /></td>
                  <td className="py-1 pr-2"><input className="dax-input" value={r.price} inputMode="decimal" onChange={(e) => setRow(r.key, { price: e.target.value })} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[11px] text-slate-500 mt-1">{rows.length} variantes además de la principal.</p>
        </div>
      )}
    </section>
  )
}
