import { useState } from 'react'

import { productsApi } from '../../api/products'
import type { Product, ProductVariant } from '../../types/products'
import { errorDetailText } from '../../utils/errorDetail'
import { ProductVariantsSection } from './ProductVariantsSection'
import { toExtraVariants, type VariantRow } from './variantMatrix'

interface Props {
  product: Product
  onChanged: (p: Product) => void
}

/**
 * Variantes existentes de un producto (edición). Cada fila guarda por su
 * cuenta con PUT /api/products/variants/{id}; el formulario de arriba sigue
 * editando solo la principal. Retirar pasa por DELETE y el backend decide
 * (409 con existencia o ventas).
 */
export function ProductVariantsEditor({ product, onChanged }: Props) {
  const [busyId, setBusyId] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [rows, setRows] = useState<VariantRow[]>([])
  const variants = product.variants ?? []

  const save = async (v: ProductVariant, patch: Parameters<typeof productsApi.updateVariant>[1]) => {
    setBusyId(v.id); setMsg(null)
    try { onChanged(await productsApi.updateVariant(v.id, patch)) }
    catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      setMsg(errorDetailText(e?.response?.data?.detail, 'No se pudo guardar la variante.'))
    } finally { setBusyId(null) }
  }

  const remove = async (v: ProductVariant) => {
    if (!window.confirm(`¿Retirar la variante ${v.variant_name ?? v.sku}?`)) return
    setBusyId(v.id); setMsg(null)
    try {
      await productsApi.deleteVariant(v.id)
      onChanged(await productsApi.getById(product.id))
    } catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      setMsg(errorDetailText(e?.response?.data?.detail, 'No se pudo retirar la variante.'))
    } finally { setBusyId(null) }
  }

  const addRows = async () => {
    if (rows.length === 0) return
    setBusyId('new'); setMsg(null)
    try {
      onChanged(await productsApi.createVariants(product.id, toExtraVariants(rows)))
      setRows([]); setAdding(false)
    } catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      setMsg(errorDetailText(e?.response?.data?.detail, 'No se pudieron crear las variantes.'))
    } finally { setBusyId(null) }
  }

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-black uppercase tracking-wide text-slate-300">Variantes ({variants.length})</h3>
      {msg && <p className="text-sm text-amber-400">{msg}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-left text-slate-400">
            <th className="py-1 pr-2">Color</th><th className="py-1 pr-2">Talla</th><th className="py-1 pr-2">SKU</th>
            <th className="py-1 pr-2">Código</th><th className="py-1 pr-2">Precio</th><th className="py-1 pr-2">Existencia</th><th />
          </tr></thead>
          <tbody>
            {variants.map((v) => (
              <VariantRowEditor key={v.id} v={v} busy={busyId === v.id} onSave={(patch) => save(v, patch)} onRemove={() => remove(v)} />
            ))}
          </tbody>
        </table>
      </div>
      {!adding ? (
        <button type="button" className="dax-btn-secondary" onClick={() => setAdding(true)}>Agregar variantes</button>
      ) : (
        <div className="space-y-2">
          <ProductVariantsSection baseSku={product.sku} rows={rows} onRowsChange={setRows} />
          <div className="flex gap-2">
            <button type="button" className="dax-btn-primary" disabled={busyId === 'new' || rows.length === 0} onClick={addRows}>Crear {rows.length} variantes</button>
            <button type="button" className="dax-btn-secondary" onClick={() => { setAdding(false); setRows([]) }}>Cancelar</button>
          </div>
        </div>
      )}
    </section>
  )
}

function VariantRowEditor({ v, busy, onSave, onRemove }: {
  v: ProductVariant; busy: boolean
  onSave: (patch: { color?: string | null; size?: string | null; sku?: string; barcode?: string | null; price?: number }) => void
  onRemove: () => void
}) {
  const [color, setColor] = useState(v.color ?? '')
  const [size, setSize] = useState(v.size ?? '')
  const [sku, setSku] = useState(v.sku)
  const [barcode, setBarcode] = useState(v.barcode ?? '')
  const [price, setPrice] = useState(String(v.price))
  const dirty = color !== (v.color ?? '') || size !== (v.size ?? '') || sku !== v.sku || barcode !== (v.barcode ?? '') || Number(price) !== Number(v.price)
  return (
    <tr>
      <td className="py-1 pr-2"><input className="dax-input" value={color} onChange={(e) => setColor(e.target.value)} /></td>
      <td className="py-1 pr-2"><input className="dax-input" value={size} onChange={(e) => setSize(e.target.value)} /></td>
      <td className="py-1 pr-2"><input className="dax-input" value={sku} onChange={(e) => setSku(e.target.value)} /></td>
      <td className="py-1 pr-2"><input className="dax-input" value={barcode} onChange={(e) => setBarcode(e.target.value)} /></td>
      <td className="py-1 pr-2"><input className="dax-input" value={price} inputMode="decimal" onChange={(e) => setPrice(e.target.value)} /></td>
      <td className="py-1 pr-2 text-slate-300">{Number(v.stock_total ?? 0)}</td>
      <td className="py-1 flex gap-1">
        <button type="button" className="dax-btn-primary" disabled={!dirty || busy}
                onClick={() => onSave({ color: color || null, size: size || null, sku, barcode: barcode || null, price: Number(price) })}>Guardar</button>
        <button type="button" className="dax-btn-secondary" disabled={busy} onClick={onRemove}>Retirar</button>
      </td>
    </tr>
  )
}
