import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import type { Product } from '../../../types/products'
import { formatCurrency } from '../../../utils/currency'
import { productsApi } from '../../../api/products'
import { inventoryApi } from '../../../api/inventory'
import { useAuthStore } from '../../../store/authStore'
import { toast } from '../../../store/toastStore'
import { Modal } from '../../ui/Modal'
import { LimiteDeError } from '../../ui/LimiteDeError'
import { variantAxisLabel, variantDisplayName, variantPrice, variantShortLabel } from '../variantPicker'

// El editor es el formulario único (FormularioProducto) en el Modal del kit;
// va en chunk propio para que no viaje en POS-*.js (presupuesto de la ruta
// crítica). POS.tsx lo precarga al entrar.
const EditarProductoPos = lazy(() => import('../EditarProductoPos'))

interface Props {
  product: Product | null
  onClose: () => void
  onAddToCart?: (product: Product) => void
  /** Se avisa cuando la ficha cambió el producto (edición o entrada de existencia): el padre recarga su grid. */
  onSaved?: (product: Product) => void
  /** Permite Editar y Agregar existencia. En modo básico llega apagado. */
  canEdit?: boolean
}

// Paleta cíclica de los escalones de precio — acomoda cualquier cantidad.
const TIER_PALETTE: Array<{ color: string; bg: string; border: string }> = [
  { color: '#047857', bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.40)' },  // emerald
  { color: '#b45309', bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.45)' },  // amber
  { color: '#6d28d9', bg: 'rgba(139,92,246,0.08)',  border: 'rgba(139,92,246,0.45)' },  // violet
  { color: '#0e7490', bg: 'rgba(6,182,212,0.08)',   border: 'rgba(6,182,212,0.40)'  },  // cyan
  { color: '#be185d', bg: 'rgba(236,72,153,0.08)',  border: 'rgba(236,72,153,0.40)' },  // pink
  { color: '#4338ca', bg: 'rgba(99,102,241,0.08)',  border: 'rgba(99,102,241,0.45)' },  // indigo
]
const paletteFor = (i: number) => TIER_PALETTE[i % TIER_PALETTE.length]

const MetaCell = ({ label, value }: { label: string; value: string | number }) => (
  <div className="rounded-lg p-2.5" style={{ background: 'var(--dax-elevated)' }}>
    <p className="text-[10px]" style={{ color: 'var(--dax-text-faint)' }}>{label}</p>
    <p className="text-xs font-semibold mt-0.5" style={{ color: 'var(--dax-text)' }}>{String(value)}</p>
  </div>
)

const ETIQUETA = 'text-[10px] font-bold uppercase tracking-wider'

/**
 * Ficha del producto en el POS (SP1-c): SOLO consulta. Existencia y precio por
 * talla, escalones, datos del catálogo, agregar al carrito y, con permiso, una
 * entrada rápida de existencia. Editar abre el formulario único
 * (`EditarProductoPos`); la ficha ya no crea ni edita por su cuenta.
 */
export function ProductDetailModal({ product, onClose, onAddToCart, onSaved, canEdit = false }: Props) {
  // Lo que el padre pasó puede quedar viejo tras un ajuste o una edición: se
  // recarga y se pinta aquí mismo, además de avisarle.
  const [refreshed, setRefreshed] = useState<Product | null>(null)
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null)
  const [editando, setEditando] = useState(false)

  // Entrada rápida de existencia (plegada; la cajera la usa al recibir mercancía).
  const [agregando, setAgregando] = useState(false)
  const [addStockQty, setAddStockQty] = useState('')
  const [addStockReason, setAddStockReason] = useState('')
  const [addStockBusy, setAddStockBusy] = useState(false)
  const [addStockMsg, setAddStockMsg] = useState<string | null>(null)

  useEffect(() => {
    setRefreshed(null)
    setEditando(false)
    setAgregando(false)
    setAddStockQty(''); setAddStockReason(''); setAddStockMsg(null)
    setSelectedVariantId(product?.matched_variant_id ?? product?.variants?.[0]?.id ?? null)
  }, [product])

  const live = refreshed ?? product
  const variantesVivas = live?.variants ?? []
  // Nombre de la talla que representa el número grande — nunca "Estándar".
  const nombreVariante = (() => {
    const v = variantesVivas.find(x => x.id === selectedVariantId)
    return v ? variantShortLabel(v) : null
  })()
  // Con varias tallas, la existencia sigue a la talla elegida, no a la que
  // empató el escaneo (o la primera).
  const selectedVariantStock = selectedVariantId
    ? variantesVivas.find(v => v.id === selectedVariantId)?.stock_total
    : undefined
  const displayStock = selectedVariantStock != null
    ? Number(selectedVariantStock)
    : Number(live?.stock_total ?? live?.stock ?? 0)

  const viewTiers = useMemo(() => {
    const raw = (live?.prices ?? [])
      .slice()
      .sort((a, b) => (a.min_quantity ?? 1) - (b.min_quantity ?? 1))
    const base = Number(live?.price ?? 0)
    const out: Array<{ key: string; name: string; min: number; value: number }> = []
    if (base > 0) out.push({ key: 'base', name: 'Base', min: 1, value: base })
    const isBaseLike = (n: string | undefined) => {
      const s = (n || '').trim().toLowerCase()
      return s === 'base' || s === 'menudeo'
    }
    for (const t of raw) {
      const min = t.min_quantity ?? 1
      if (base > 0 && min <= 1 && isBaseLike(t.price_name)) continue
      out.push({ key: String(t.id), name: t.price_name, min, value: Number(t.unit_price ?? 0) })
    }
    return out
  }, [live])

  if (!product || !live) return null

  const titulo = live.sale_name ?? live.name

  const recargar = async (fallback: Product) => {
    try {
      const fresh = await productsApi.getById(product.id)
      setRefreshed({ ...fresh, matched_variant_id: product.matched_variant_id ?? fresh.matched_variant_id })
      onSaved?.(fresh)
    } catch {
      // El cambio sí se aplicó: no se puede fallar aquí. El padre recarga.
      onSaved?.(fallback)
    }
  }

  const addStock = async () => {
    if (!selectedVariantId) { setAddStockMsg('Producto sin variante — no se puede ajustar stock'); return }
    const qty = Number(addStockQty)
    if (!(qty > 0)) { setAddStockMsg('Cantidad debe ser > 0'); return }
    const userBranchId = useAuthStore.getState().user?.branch_id
    if (!userBranchId) { setAddStockMsg('Tu usuario no tiene sucursal asignada'); return }
    setAddStockBusy(true)
    setAddStockMsg(null)
    try {
      await inventoryApi.createAdjustment({
        variant_id: selectedVariantId,
        quantity: qty,
        branch_id: userBranchId,
        reason: addStockReason.trim() || 'Reposición POS',
      })
      setAddStockQty('')
      setAddStockReason('')
      setAddStockMsg(`+${qty} agregadas al stock`)
      await recargar(product)
    } catch (e: any) {
      setAddStockMsg(e?.response?.data?.detail ?? 'Error al ajustar stock')
    } finally {
      setAddStockBusy(false)
    }
  }

  const pie = (
    <>
      <button type="button" onClick={onClose} className="flex-1 dax-btn-secondary text-sm justify-center">
        Cerrar
      </button>
      {onAddToCart && displayStock > 0 && (
        <button
          type="button"
          onClick={() => { onAddToCart(product); onClose() }}
          aria-label="Agregar al carrito"
          className="flex-1 dax-btn-primary text-sm justify-center"
        >
          <i className="fa-solid fa-cart-plus" aria-hidden="true" /> Agregar
        </button>
      )}
    </>
  )

  // Con el editor encima, ni Escape ni el fondo cierran la ficha: cerrarla
  // desmontaría el editor y tiraría lo capturado.
  return (
    <Modal open onClose={onClose} title={titulo} size="md" footer={pie} closeOnEscape={!editando} closeOnBackdrop={!editando}>
      <div className="space-y-4">
        {/* Foto */}
        <div className="-mx-5 -mt-4 h-40 flex items-center justify-center" style={{ background: 'var(--dax-elevated)' }}>
          {live.image_url ? (
            <img src={live.image_url} alt="" className="w-full h-full object-cover" />
          ) : (
            <i className="fa-solid fa-box text-5xl" style={{ color: 'var(--dax-text-faint)' }} />
          )}
        </div>

        {/* SKU + Editar */}
        <div className="flex items-start justify-between gap-2">
          <p className="text-xs font-mono" style={{ color: 'var(--dax-text-faint)' }}>{live.sku}</p>
          {canEdit && (
            <button
              type="button"
              onClick={() => setEditando(true)}
              className="dax-btn-secondary text-xs max-md:min-h-[44px]"
              title="Editar producto"
            >
              <i className="fa-solid fa-pen text-[11px]" aria-hidden="true" /> Editar
            </button>
          )}
        </div>

        {/* Existencia */}
        <div className="space-y-2">
          <div className="flex items-center justify-end gap-2">
            {/* Sin el nombre, "12 en stock" era el de una talla cualquiera y nadie sabía de cuál hablaba. */}
            {variantesVivas.length > 1 && nombreVariante && (
              <span className="text-[11px] font-bold px-2 py-0.5 rounded-full"
                    style={{ background: 'var(--dax-accent-soft)', color: 'var(--dax-accent-text)' }}>
                {nombreVariante}
              </span>
            )}
            <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${
              displayStock > 0 ? 'bg-emerald-600/20 text-emerald-700' : 'bg-red-600/20 text-red-600'
            }`}>
              {displayStock > 0 ? `${displayStock} en stock` : 'Sin stock'}
            </span>
          </div>

          {/* Existencia y precio de TODAS las tallas: lo que la cajera necesita
              para contestar "¿y en M?" sin salir de la ficha. */}
          {variantesVivas.length > 1 && (
            <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--dax-border-dim)' }}>
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ background: 'var(--dax-elevated)' }}>
                    <th className="text-left font-bold px-2 py-1.5" style={{ color: 'var(--dax-text-muted)' }}>
                      {variantAxisLabel(variantesVivas)}
                    </th>
                    <th className="text-right font-bold px-2 py-1.5" style={{ color: 'var(--dax-text-muted)' }}>Existencia</th>
                    <th className="text-right font-bold px-2 py-1.5" style={{ color: 'var(--dax-text-muted)' }}>Precio</th>
                  </tr>
                </thead>
                <tbody>
                  {variantesVivas.map((v) => {
                    const s = Number(v.stock_total ?? 0)
                    const esActual = v.id === selectedVariantId
                    return (
                      <tr key={v.id} style={{ borderTop: '1px solid var(--dax-border-dim)', background: esActual ? 'rgba(99,102,241,0.08)' : undefined }}>
                        <td className="px-2 py-1.5 font-semibold" style={{ color: 'var(--dax-text)' }}>
                          {v.sale_name ?? variantDisplayName(v, live.name)}
                        </td>
                        <td className={`px-2 py-1.5 text-right font-bold tabular-nums ${s > 0 ? '' : 'text-red-600'}`}
                            style={s > 0 ? { color: 'var(--dax-text)' } : undefined}>
                          {s > 0 ? s : 'sin existencia'}
                        </td>
                        {/* Precio de la SUCURSAL (`effective_price`): el que cobra el ticket cuando hay override. */}
                        <td className="px-2 py-1.5 text-right font-bold tabular-nums" style={{ color: 'var(--dax-text)' }}>
                          {formatCurrency(variantPrice(v))}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Entrada rápida de existencia (con permiso), plegada hasta que se pide. */}
          {canEdit && !agregando && (
            <button
              type="button"
              onClick={() => setAgregando(true)}
              className="dax-btn-secondary text-xs w-full justify-center max-md:min-h-[44px]"
            >
              <i className="fa-solid fa-plus" aria-hidden="true" /> Agregar existencia
            </button>
          )}
          {canEdit && agregando && (
            <div className="rounded-lg p-3" style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)' }}>
              <p className={`${ETIQUETA} mb-2`} style={{ color: 'var(--dax-text-muted)' }}>Agregar existencia</p>
              {variantesVivas.length > 1 && (
                <label className="block mb-2">
                  <span className="text-[9px] font-bold uppercase tracking-wider block mb-1" style={{ color: 'var(--dax-text-faint)' }}>
                    {variantAxisLabel(variantesVivas)} a ajustar
                  </span>
                  <select
                    className="dax-input w-full text-xs"
                    value={selectedVariantId ?? ''}
                    onChange={e => setSelectedVariantId(e.target.value || null)}
                  >
                    {variantesVivas.map(v => (
                      <option key={v.id} value={v.id}>
                        {v.sale_name ?? variantDisplayName(v, live.name)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-[1fr_2fr_auto] gap-2 items-end">
                <label className="block">
                  <span className="text-[9px] font-bold uppercase tracking-wider block mb-1" style={{ color: 'var(--dax-text-faint)' }}>
                    Cantidad
                  </span>
                  <input
                    type="number"
                    min="1"
                    step="1"
                    className="dax-input w-full text-center font-bold"
                    value={addStockQty}
                    onChange={e => setAddStockQty(e.target.value)}
                    placeholder="0"
                  />
                </label>
                <label className="block">
                  <span className="text-[9px] font-bold uppercase tracking-wider block mb-1" style={{ color: 'var(--dax-text-faint)' }}>
                    Motivo
                  </span>
                  <input
                    type="text"
                    className="dax-input w-full"
                    value={addStockReason}
                    onChange={e => setAddStockReason(e.target.value)}
                    placeholder="Ej. Compra, Reposición"
                  />
                </label>
                <button
                  type="button"
                  onClick={addStock}
                  disabled={addStockBusy || !addStockQty}
                  aria-label="Registrar entrada"
                  className="dax-btn-primary text-xs px-3 py-2 disabled:opacity-40 whitespace-nowrap justify-center max-md:min-h-[44px]"
                >
                  {addStockBusy ? <i className="fa-solid fa-spinner fa-spin" aria-hidden="true" /> : <><i className="fa-solid fa-plus" aria-hidden="true" /> Agregar</>}
                </button>
              </div>
              {addStockMsg && (
                <p className="text-[10px] mt-2 font-semibold" style={{ color: addStockMsg.startsWith('+') ? '#047857' : '#dc2626' }}>
                  {addStockMsg}
                </p>
              )}
              {!selectedVariantId && (
                <p className="text-[9px] mt-1" style={{ color: 'var(--dax-text-faint)' }}>
                  Producto sin variante — no se puede ajustar stock.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Escalones de precio */}
        {viewTiers.length > 0 && (
          <div>
            <p className={`${ETIQUETA} mb-1.5`} style={{ color: 'var(--dax-text-faint)' }}>Precios disponibles</p>
            <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${Math.min(viewTiers.length, 3)}, minmax(0, 1fr))` }}>
              {viewTiers.map((pr, i) => {
                const meta = paletteFor(i)
                return (
                  <div key={pr.key} className="rounded-lg p-2 flex flex-col items-center justify-center"
                       style={{ background: meta.bg, border: `1px solid ${meta.border}` }}>
                    <span className="text-[9px] font-bold uppercase tracking-wider" style={{ color: meta.color }}>{pr.name}</span>
                    <span className="text-sm font-black tabular-nums" style={{ color: meta.color }}>{formatCurrency(pr.value)}</span>
                    {pr.min > 1 && (
                      <span className="text-[9px] mt-0.5" style={{ color: 'var(--dax-text-faint)' }}>mín. {pr.min}u</span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Datos del catálogo */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          {live.brand_name && <MetaCell label="Marca" value={live.brand_name} />}
          {live.department_name && <MetaCell label="Departamento" value={live.department_name} />}
          {live.min_stock != null && <MetaCell label="Stock mín." value={live.min_stock} />}
          {live.barcode && <MetaCell label="Código de barras" value={live.barcode} />}
          <MetaCell label="IVA" value={live.has_iva ? `Con IVA ${live.tax_rate ?? 16}%` : 'Sin IVA'} />
        </div>

        {live.description && (
          <p className="text-sm leading-relaxed" style={{ color: 'var(--dax-text-muted)' }}>{live.description}</p>
        )}
      </div>

      {/* Editor (formulario único) encima de la ficha. Un chunk viejo tras un
          deploy no tira el POS: el límite lo contiene y avisa. */}
      {editando && (
        <LimiteDeError onError={() => {
          setEditando(false)
          toast.error('No se pudo abrir el editor del producto. Recarga la página.')
        }}>
          <Suspense fallback={null}>
            <EditarProductoPos
              productId={product.id}
              variantId={selectedVariantId}
              onClose={() => setEditando(false)}
              onGuardado={(p) => {
                setRefreshed({ ...p, matched_variant_id: product.matched_variant_id ?? p.matched_variant_id })
                setEditando(false)
                onSaved?.(p)
              }}
            />
          </Suspense>
        </LimiteDeError>
      )}
    </Modal>
  )
}
