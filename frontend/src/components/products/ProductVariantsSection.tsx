import { useEffect, useState } from 'react'

import type { ProductErrors } from './types'
import { buildVariantRows, parseList, type VariantPair, type VariantRow } from './variantMatrix'
import { usesColors, variantWords } from './variantWords'

interface Props {
  baseSku: string
  rows: VariantRow[]
  onRowsChange: (rows: VariantRow[]) => void
  /** Alta de producto: la PRIMERA fila es la variante principal (SKU base,
   *  código y precio de los campos de arriba), no una hermana más. En la
   *  edición (agregar variantes a un producto que ya existe) va en false:
   *  ahí la principal ya está creada y todas las filas son hermanas. */
  firstIsPrincipal?: boolean
  /** Errores del formulario: `variants.<N>.sku` / `variants.<N>.price`, donde
   *  N es el índice entre las hermanas (la principal no cuenta). */
  errors?: ProductErrors
  /** Columna "Existencia inicial" por fila (alta). */
  showInitialStock?: boolean
  /** Existencia de la principal: es el campo "Stock inicial" del formulario. */
  principalStock?: string
  onPrincipalStockChange?: (value: string) => void
  /** Nombre de la sucursal a la que entra esa existencia. */
  stockBranchName?: string | null
  /** Parejas color/talla que el producto YA tiene (edición): no se regeneran. */
  existing?: VariantPair[]
  /** Texto inicial de los campos colores/tallas (edición: lo ya creado). */
  defaultColors?: string
  defaultSizes?: string
}

/**
 * Matriz color × talla (preset boutique). El admin escribe los colores y las
 * tallas separados por coma; cada combinación es una variante con su SKU
 * sugerido, su código de barras, su precio y su existencia inicial.
 *
 * En el alta (`firstIsPrincipal`), la primera combinación ES la variante
 * principal: usa el SKU base y los campos de arriba, y no se manda como
 * variante extra. Así una prenda con S/M/L nace con tres variantes y no con
 * cuatro (la vieja "Estándar" sin talla que el POS mostraba como "—").
 */
export function ProductVariantsSection({
  baseSku, rows, onRowsChange, firstIsPrincipal = false, errors = {},
  showInitialStock = false, principalStock = '', onPrincipalStockChange,
  stockBranchName, existing = [], defaultColors = '', defaultSizes = '',
}: Props) {
  const [colors, setColors] = useState(defaultColors)
  const [sizes, setSizes] = useState(defaultSizes)

  const regenerate = (c: string, s: string) => {
    onRowsChange(buildVariantRows(baseSku, parseList(c), parseList(s), rows, existing))
  }
  const setRow = (key: string, patch: Partial<VariantRow>) => {
    onRowsChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  }

  // El SKU sugerido de cada fila se compone con el SKU base: al cambiarlo hay
  // que recalcularlo o las filas se quedan con el prefijo viejo (lo respeta
  // `buildVariantRows`, que no pisa las filas con el SKU escrito a mano).
  // Regenerar solo cuando ya hay filas evita crear filas de la nada a partir
  // de un baseSku vacío.
  useEffect(() => {
    if (rows.length > 0) regenerate(colors, sizes)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseSku])

  const conColores = usesColors(existing) || parseList(colors).length > 0
  const palabra = variantWords(conColores)
  const titulo = conColores ? 'Variantes (color / talla)' : 'Tallas'

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-black uppercase tracking-wide text-slate-300">{titulo}</h3>
      <p className="text-[11px] text-slate-500">
        Escribe colores y tallas separados por coma. Cada combinación se crea como una {palabra.singular} con su
        propio código y existencia. Si la prenda no tiene {palabra.plural}, deja esto vacío.
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
                <th className="py-1 pr-2">{conColores ? 'Variante' : 'Talla'}</th>
                <th className="py-1 pr-2">SKU</th>
                <th className="py-1 pr-2">Código de barras</th>
                <th className="py-1 pr-2">Precio (vacío = base)</th>
                {showInitialStock && <th className="py-1 pr-2">Existencia inicial</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const esPrincipal = firstIsPrincipal && i === 0
                // Los errores se numeran entre las hermanas: la principal no
                // viaja en `extra_variants`, así que no tiene índice propio.
                const n = firstIsPrincipal ? i - 1 : i
                const errSku = esPrincipal ? undefined : errors[`variants.${n}.sku`]
                const errPrecio = esPrincipal ? undefined : errors[`variants.${n}.price`]
                const errStock = esPrincipal ? undefined : errors[`variants.${n}.initial_stock`]
                return (
                  <tr key={r.key}>
                    <td className="py-1 pr-2 font-semibold text-slate-200">{[r.color, r.size].filter(Boolean).join(' / ')}</td>
                    <td className="py-1 pr-2">
                      <input className="dax-input" value={esPrincipal ? baseSku : r.sku} disabled={esPrincipal}
                             onChange={(e) => setRow(r.key, { sku: e.target.value, skuTocado: true })} />
                      {esPrincipal && <span className="text-[11px] text-slate-500 block">principal · SKU base</span>}
                      {errSku && <span className="text-rose-400 text-[11px] block">{errSku}</span>}
                    </td>
                    <td className="py-1 pr-2">
                      {esPrincipal
                        ? <span className="text-slate-500">código de arriba</span>
                        : <input className="dax-input" value={r.barcode} inputMode="numeric" onChange={(e) => setRow(r.key, { barcode: e.target.value })} />}
                    </td>
                    <td className="py-1 pr-2">
                      {esPrincipal
                        ? <span className="text-slate-500">precio base</span>
                        : <>
                            <input className="dax-input" value={r.price} inputMode="decimal" onChange={(e) => setRow(r.key, { price: e.target.value })} />
                            {errPrecio && <span className="text-rose-400 text-[11px] block">{errPrecio}</span>}
                          </>}
                    </td>
                    {showInitialStock && (
                      <td className="py-1 pr-2">
                        {esPrincipal
                          ? <input className="dax-input" value={principalStock} inputMode="decimal" min="0"
                                   onChange={(e) => onPrincipalStockChange?.(e.target.value)} />
                          : <>
                              <input className="dax-input" value={r.initial_stock} inputMode="decimal" min="0"
                                     onChange={(e) => setRow(r.key, { initial_stock: e.target.value })} />
                              {errStock && <span className="text-rose-400 text-[11px] block">{errStock}</span>}
                            </>}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
          {showInitialStock && (
            <p className="text-[11px] text-slate-500 mt-1">
              Existencia inicial por {conColores ? 'variante' : 'talla'}
              {stockBranchName ? ` en ${stockBranchName}` : ' en la sucursal seleccionada'}. Déjala en cero si aún no
              recibes la mercancía.
            </p>
          )}
          <p className="text-[11px] text-slate-500 mt-1">
            {firstIsPrincipal
              ? `${rows.length} ${palabra.plural} en total (la primera es la principal).`
              : `${rows.length} ${palabra.plural} además de la principal.`}
          </p>
        </div>
      )}
    </section>
  )
}
