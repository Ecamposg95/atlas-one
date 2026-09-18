import { useEffect, useRef, useState } from 'react'

import { productsApi } from '../../../api/products'
import type { Product, ProductVariant } from '../../../types/products'
import { formatCurrency } from '../../../utils/currency'
import { groupVariants, sizeOnly, variantAxisLabel, variantShortLabel } from '../variantPicker'

interface Props {
  product: Product
  onPick: (v: ProductVariant) => void
  onClose: () => void
}

/**
 * Elige la talla (o color × talla) antes de mandar la línea al carrito.
 *
 * Recarga el producto con GET /api/products/{id} porque la búsqueda del POS
 * puede traer la colección de variantes incompleta (eager-load filtrado por el
 * término).
 *
 * Cada opción dice las tres cosas que el cajero necesita para decidir —talla,
 * existencia y precio— porque el precio puede cambiar entre tallas y antes
 * vivía escondido en el `title` del botón, invisible en una pantalla táctil.
 */
export function VariantPickerModal({ product, onPick, onClose }: Props) {
  const [full, setFull] = useState<Product>(product)
  const cardRef = useRef<HTMLDivElement>(null)
  // Foco inicial dentro del diálogo: el tabulador seguía en la pantalla de atrás.
  useEffect(() => { cardRef.current?.focus() }, [])
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

  const variantes = full.variants ?? []
  const g = groupVariants(variantes)
  // Sin colores capturados la cuadrícula sobra: una columna de "—" y nada más.
  const soloTallas = sizeOnly(variantes) || g.colors.every((c) => !c.trim())
  const etiqueta = variantAxisLabel(variantes)

  // En la cuadrícula la identidad ya la dan la fila y la columna; repetir
  // "Rojo / M" dentro de la celda solo la ensancha.
  const celda = (v: ProductVariant, conNombre: boolean) => {
    const stock = Number(v.stock_total ?? 0)
    const agotada = stock <= 0
    return (
      <button
        type="button"
        disabled={agotada}
        onClick={() => onPick(v)}
        className="w-full min-h-[44px] rounded-lg px-2 py-2 flex flex-col items-center justify-center gap-0.5 disabled:opacity-40"
        style={{ background: 'var(--dax-elevated)', color: 'var(--dax-text)' }}
        title={v.sku}
      >
        {conNombre && (
          <span className="text-sm font-black leading-none">
            {variantShortLabel(v) ?? full.name}
          </span>
        )}
        <span className="text-[11px] font-semibold leading-none" style={{ color: agotada ? '#dc2626' : 'var(--dax-text-muted)' }}>
          {agotada ? 'sin existencia' : `${stock} pz`} · {formatCurrency(Number(v.price))}
        </span>
      </button>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60" onClick={onClose}>
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Elige la ${variantAxisLabel(variantes).toLowerCase()} de ${full.name}`}
        tabIndex={-1}
        className="w-full max-w-lg rounded-2xl p-4 outline-none"
        style={{ background: 'var(--dax-surface)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-black" style={{ color: 'var(--dax-text)' }}>{full.name}</h3>
        <p className="text-xs mb-3" style={{ color: 'var(--dax-text-muted)' }}>
          Elige la {etiqueta.toLowerCase()}
        </p>

        {soloTallas ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {variantes.map((v) => <div key={v.id}>{celda(v, true)}</div>)}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr>
                <th />
                {g.sizes.map((s) => (
                  <th key={s} className="py-1 px-1 text-center" style={{ color: 'var(--dax-text-muted)' }}>{s || '—'}</th>
                ))}
              </tr></thead>
              <tbody>
                {g.colors.map((c) => (
                  <tr key={c}>
                    <td className="py-1 pr-2 font-semibold" style={{ color: 'var(--dax-text)' }}>{c || '—'}</td>
                    {g.sizes.map((s) => {
                      const v = g.at(c, s)
                      return (
                        <td key={s} className="py-1 px-1 text-center">
                          {v ? celda(v, false) : <span style={{ color: 'var(--dax-text-faint)' }}>·</span>}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="text-[11px] mt-2" style={{ color: 'var(--dax-text-faint)' }}>
          Existencia y precio son los de tu sucursal.
        </p>
        <button type="button" className="dax-btn-secondary mt-3 w-full" onClick={onClose}>Cancelar</button>
      </div>
    </div>
  )
}
