import { useEffect, useState } from 'react'

import { productsApi } from '../../../api/products'
import type { Product, ProductVariant } from '../../../types/products'
import { formatCurrency } from '../../../utils/currency'
import { groupVariants } from '../variantPicker'

interface Props {
  product: Product
  onPick: (v: ProductVariant) => void
  onClose: () => void
}

/**
 * Cuadrícula color × talla con la existencia de cada celda. Recarga el
 * producto con GET /api/products/{id} porque la búsqueda del POS puede traer
 * la colección de variantes incompleta (eager-load filtrado por el término).
 */
export function VariantPickerModal({ product, onPick, onClose }: Props) {
  const [full, setFull] = useState<Product>(product)
  useEffect(() => {
    let cancelled = false
    productsApi.getById(product.id).then((p) => { if (!cancelled) setFull(p) }).catch(() => {})
    return () => { cancelled = true }
  }, [product.id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const g = groupVariants(full.variants ?? [])
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl p-4" style={{ background: 'var(--dax-surface)' }} onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-black" style={{ color: 'var(--dax-text)' }}>{full.name}</h3>
        <p className="text-xs mb-3" style={{ color: 'var(--dax-text-muted)' }}>Elige la variante</p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr>
              <th />
              {g.sizes.map((s) => <th key={s} className="py-1 px-1 text-center" style={{ color: 'var(--dax-text-muted)' }}>{s || '—'}</th>)}
            </tr></thead>
            <tbody>
              {g.colors.map((c) => (
                <tr key={c}>
                  <td className="py-1 pr-2 font-semibold" style={{ color: 'var(--dax-text)' }}>{c || '—'}</td>
                  {g.sizes.map((s) => {
                    const v = g.at(c, s)
                    const stock = Number(v?.stock_total ?? 0)
                    return (
                      <td key={s} className="py-1 px-1 text-center">
                        {v ? (
                          <button type="button" disabled={stock <= 0} onClick={() => onPick(v)}
                                  className="w-full rounded-lg px-2 py-2 font-bold disabled:opacity-40"
                                  style={{ background: 'var(--dax-elevated)', color: 'var(--dax-text)' }}
                                  title={`${v.sku} · ${formatCurrency(Number(v.price))}`}>
                            {stock}
                          </button>
                        ) : <span style={{ color: 'var(--dax-text-faint)' }}>·</span>}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[11px] mt-2" style={{ color: 'var(--dax-text-faint)' }}>El número es la existencia en tu sucursal.</p>
        <button type="button" className="dax-btn-secondary mt-3 w-full" onClick={onClose}>Cancelar</button>
      </div>
    </div>
  )
}
