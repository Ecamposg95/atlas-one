import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuthStore } from '../../store/authStore'
import { productsApi } from '../../api/products'
import { inventoryApi } from '../../api/inventory'
import { toast } from '../../store/toastStore'
import { ui, brand, fmtMoney } from './branchUI'
import type { Product, CatalogKpis, UploadPreviewResponse } from '../../types/products'
import { expandVariantRows } from '../../pages/inventory/variantRows'

import { TablaDesplazable } from '../ui/TablaDesplazable'
import { Modal as ModalFormulario } from '../ui/Modal'
import { FormularioProducto } from '../products/FormularioProducto'

// ─── Types ────────────────────────────────────────────────────────────────────

// Un renglón por variante — con varias tallas, cada renglón lleva su propio
// variant_id para que "Ajustar stock" no siempre pegue a la primera variante.
// `label` es la etiqueta a mostrar (con variante si aplica); `name` se deja
// intacto como el nombre real del producto (lo usa el prefill del editor).
interface ProductRow extends Product {
  variant_id?: string
  label: string
}

// ─── Tier palette + SectionHeader ─────────────────────────────────────────────

const TIER_PALETTE = [
  { bg: 'bg-purple-500/10',  border: 'border-purple-500/30',  text: 'text-purple-700 dark:text-purple-300',   icon: 'fa-tag' },
  { bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', text: 'text-emerald-700 dark:text-emerald-300', icon: 'fa-layer-group' },
  { bg: 'bg-amber-500/10',   border: 'border-amber-500/30',   text: 'text-amber-700 dark:text-amber-300',     icon: 'fa-box' },
  { bg: 'bg-indigo-500/10',  border: 'border-indigo-500/30',  text: 'text-indigo-700 dark:text-indigo-300',   icon: 'fa-warehouse' },
  { bg: 'bg-rose-500/10',    border: 'border-rose-500/30',    text: 'text-rose-700 dark:text-rose-300',       icon: 'fa-percent' },
] as const

function tierStyle(i: number) {
  return TIER_PALETTE[Math.min(i, TIER_PALETTE.length - 1)]
}

function SectionHeader({ icon, label, accentColor }: {
  icon: string
  label: string
  accentColor: 'slate' | 'purple' | 'blue'
}) {
  const colorClass = {
    slate: 'text-slate-500',
    purple: 'text-purple-500',
    blue: 'text-blue-500',
  }[accentColor]
  return (
    <div className="flex items-center gap-2 mb-3">
      <i className={`fa-solid ${icon} ${colorClass}`} aria-hidden="true" />
      <p className="text-xs font-bold uppercase tracking-widest text-slate-700 dark:text-slate-300">
        {label}
      </p>
    </div>
  )
}

// ─── KpiCard ──────────────────────────────────────────────────────────────────

interface KpiCardProps {
  icon: string
  label: string
  value: string
  valueClass?: string
  iconBg?: string
  iconColor?: string
}

function KpiCard({ icon, label, value, valueClass, iconBg, iconColor }: KpiCardProps) {
  return (
    <div className={`${ui.card} p-5 flex flex-col gap-1`}>
      <div className="flex items-center gap-2">
        <div
          className="flex items-center justify-center w-7 h-7 rounded-lg flex-shrink-0"
          style={{ background: iconBg ?? 'rgba(139,92,246,0.12)' }}
        >
          <i className={`fa-solid ${icon} text-sm`} style={{ color: iconColor ?? '#a78bfa' }} />
        </div>
        <span className={ui.kpiLabel}>{label}</span>
      </div>
      <span className={`${ui.kpiValue} text-2xl ${valueClass ?? ''}`}>{value}</span>
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export function ProductsBranchView() {
  const { user } = useAuthStore()
  const branchId = user?.branch_id ?? null

  const [items, setItems] = useState<ProductRow[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'low'>('all')
  const [kpis, setKpis] = useState<CatalogKpis | null>(null)

  // Qué renglón se está editando: el producto completo + la talla de la que
  // salió la fila. Sin el `variantId`, el formulario escribía siempre la
  // identidad de la principal.
  const [editing, setEditing] = useState<{ productId: string; variantId?: string } | null>(null)
  const [creating, setCreating] = useState(false)
  const [stockTarget, setStockTarget] = useState<ProductRow | null>(null)
  const [showImport, setShowImport] = useState(false)
  const [fichaTarget, setFichaTarget] = useState<ProductRow | null>(null)

  // ── Load ───────────────────────────────────────────────────────────────────
  const load = useCallback(async (q: string) => {
    setLoading(true)
    try {
      const res = await productsApi.list({ search: q, limit: 100 })
      const rows: ProductRow[] = expandVariantRows(res.items ?? []).map((row) => ({
        ...row.product,
        label: row.label,
        sku: row.sku,
        barcode: row.barcode,
        // El precio con override de sucursal vive en row.product.price (el backend lo aplica
        // ahí), no en variant.price — usar variant.price perdería el override por sucursal.
        price: row.product.price,
        stock_total: row.qty,
        // Sin variantes reales no hay a qué ajustar — deja variant_id sin definir para que
        // el modal de ajuste muestre "Producto sin variante" en vez de mandar el UUID del producto.
        variant_id: (row.product.variants && row.product.variants.length > 0) ? row.variant.id : undefined,
      }))
      setItems(rows)
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'No se pudo cargar el catálogo')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  const loadKpis = useCallback(() => {
    productsApi.getCatalogKpis().then(setKpis).catch(() => {})
  }, [])

  useEffect(() => {
    loadKpis()
  }, [loadKpis])

  useEffect(() => {
    const id = setTimeout(() => load(search), 250)
    return () => clearTimeout(id)
  }, [search, load])

  // ── Filtered view ──────────────────────────────────────────────────────────
  const visible = useMemo(() => {
    if (filter === 'all') return items
    if (filter === 'low') {
      return items.filter((p) => {
        const min = p.min_stock ?? 0
        const qty = p.stock_total ?? p.stock ?? 0
        return qty <= min
      })
    }
    return items
  }, [items, filter])

  // ── Edit: cargar producto completo (con prices + packaging_units) ─────────
  function openEdit(p: ProductRow) {
    setEditing({ productId: p.id, variantId: p.variant_id })
  }

  // ── Excel template + import ────────────────────────────────────────────────
  async function downloadTemplate() {
    try {
      await productsApi.downloadTemplate()
      toast.success('Plantilla descargada')
    } catch {
      toast.error('No se pudo descargar la plantilla')
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className={`${ui.page} py-6`}>
      <div className={`${ui.container} space-y-5`}>

        {/* Hero */}
        <div className={`${ui.hero} px-6 py-6 flex flex-wrap items-center justify-between gap-4`}>
          <div>
            <p className="text-white/70 text-xs font-semibold uppercase tracking-widest mb-0.5">
              Mi sucursal
            </p>
            <h1 className="text-2xl lg:text-3xl font-bold text-white">Inventario</h1>
            <p className="text-white/70 text-xs mt-1">{visible.length} productos</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={downloadTemplate}
              className="inline-flex items-center gap-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-xs font-semibold px-3 py-2.5 transition-colors"
              title="Descargar plantilla Excel"
            >
              <i className="fa-solid fa-file-arrow-down" />
              Plantilla
            </button>
            <button
              onClick={() => setShowImport(true)}
              className="inline-flex items-center gap-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-xs font-semibold px-3 py-2.5 transition-colors"
              title="Importar productos desde Excel"
            >
              <i className="fa-solid fa-file-import" />
              Importar Excel
            </button>
            <button
              onClick={() => setCreating(true)}
              className="inline-flex items-center gap-2 rounded-xl bg-white text-purple-700 hover:bg-white/90 active:bg-white/80 text-sm font-bold px-4 py-2.5 transition-colors"
            >
              <i className="fa-solid fa-plus" />
              Nuevo producto
            </button>
          </div>
        </div>

        {/* ── KPIs por sucursal — 4 cards ───────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <KpiCard
            icon="fa-cubes"
            label="Total productos"
            value={kpis ? String(kpis.total_skus) : '—'}
            iconBg="rgba(148,163,184,0.15)"
            iconColor="#94a3b8"
          />
          <KpiCard
            icon="fa-store"
            label="Activos en POS"
            value={kpis ? String(kpis.active_pos) : '—'}
            iconBg="rgba(16,185,129,0.12)"
            iconColor="#10b981"
            valueClass="text-emerald-600 dark:text-emerald-400"
          />
          <KpiCard
            icon="fa-triangle-exclamation"
            label="Stock crítico"
            value={kpis ? String(kpis.critical_stock) : '—'}
            iconBg="rgba(245,158,11,0.12)"
            iconColor="#f59e0b"
            valueClass="text-amber-600 dark:text-amber-400"
          />
          <KpiCard
            icon="fa-circle-xmark"
            label="Sin stock"
            value={kpis ? String(kpis.zero_stock) : '—'}
            iconBg="rgba(244,63,94,0.12)"
            iconColor="#f43f5e"
            valueClass="text-rose-600 dark:text-rose-400"
          />
        </div>

        {/* Search + filters */}
        <div className={`${ui.card} p-4 flex flex-wrap items-center gap-3`}>
          <div className="relative flex-1 min-w-[220px]">
            <i className="fa-solid fa-search absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-sm" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por nombre, SKU o código de barras…"
              className={`${ui.input} pl-11`}
            />
          </div>
          <div className="flex gap-1 bg-stone-100 dark:bg-slate-800 rounded-xl p-1">
            {(['all', 'low'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                  filter === f
                    ? 'bg-purple-600 text-white shadow'
                    : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                {f === 'all' ? 'Todos' : 'Stock bajo'}
              </button>
            ))}
          </div>
        </div>

        {/* List */}
        {loading ? (
          <div className={`${ui.card} p-12 flex items-center justify-center`}>
            <i className="fa-solid fa-spinner fa-spin text-2xl text-purple-500" />
          </div>
        ) : visible.length === 0 ? (
          <div className={`${ui.card} p-12 text-center`}>
            <i className="fa-solid fa-box-open text-4xl text-slate-400 mb-3 block" />
            <p className={`text-sm ${ui.muted}`}>
              {search ? 'Sin resultados para tu búsqueda' : 'Todavía no hay productos en tu sucursal'}
            </p>
          </div>
        ) : (
          <div className={`${ui.card} overflow-hidden`}>
            <ul className="divide-y divide-stone-200 dark:divide-slate-800">
              {visible.map((p) => (
                <ProductRow
                  key={p.variant_id ?? p.id}
                  product={p}
                  onView={() => setFichaTarget(p)}
                  onEdit={() => openEdit(p)}
                  onStock={() => setStockTarget(p)}
                />
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Modals */}
      {creating && (
        <ModalFormulario open onClose={() => setCreating(false)} size="xl" closeOnBackdrop={false} title="Nuevo producto">
          <FormularioProducto mode="create" presentacion="modal"
            onDone={() => { setCreating(false); load(search); loadKpis() }}
            onCancel={() => setCreating(false)} />
        </ModalFormulario>
      )}
      {editing && (
        <ModalFormulario open onClose={() => setEditing(null)} size="xl" closeOnBackdrop={false} title="Editar producto">
          <FormularioProducto mode="edit" productId={editing.productId} variantId={editing.variantId} presentacion="modal"
            onDone={() => { setEditing(null); load(search); loadKpis() }}
            onCancel={() => setEditing(null)} />
        </ModalFormulario>
      )}
      {stockTarget && (
        <StockAdjustModal
          product={stockTarget}
          onClose={() => setStockTarget(null)}
          onSaved={() => { setStockTarget(null); load(search); loadKpis() }}
        />
      )}
      {showImport && (
        <ImportExcelModal
          onClose={() => setShowImport(false)}
          onDone={() => { setShowImport(false); load(search); loadKpis() }}
        />
      )}
      {fichaTarget && (
        <ProductFichaModal
          product={fichaTarget}
          onClose={() => setFichaTarget(null)}
          onEdit={() => { const p = fichaTarget; setFichaTarget(null); openEdit(p) }}
          onAdjustStock={() => { const p = fichaTarget; setFichaTarget(null); setStockTarget(p) }}
        />
      )}
    </div>
  )
}

// ─── Row ──────────────────────────────────────────────────────────────────────

interface RowProps {
  product: ProductRow
  onView: () => void
  onEdit: () => void
  onStock: () => void
}

function ProductRow({ product: p, onView, onEdit, onStock }: RowProps) {
  const stock = Number(p.stock_total ?? p.stock ?? 0)
  const min = p.min_stock ?? 0
  const lowStock = min > 0 && stock <= min

  return (
    <li
      onClick={onView}
      className="p-4 flex items-center gap-4 hover:bg-stone-50 dark:hover:bg-slate-800/40 transition-colors cursor-pointer"
    >
      {/* Image / placeholder */}
      <div className="w-12 h-12 rounded-xl bg-stone-100 dark:bg-slate-800 flex items-center justify-center flex-shrink-0 overflow-hidden">
        {p.image_url ? (
          <img src={p.image_url} alt="" loading="lazy" className="w-full h-full object-cover" />
        ) : (
          <i className="fa-solid fa-box text-slate-400" />
        )}
      </div>

      {/* Name + meta */}
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-slate-900 dark:text-slate-100 truncate">{p.label}</p>
        <p className="text-xs text-slate-500 dark:text-slate-400 truncate font-mono">
          {p.sku}{p.brand_name ? ` · ${p.brand_name}` : ''}
        </p>
      </div>

      {/* Price */}
      <div className="text-right hidden sm:flex flex-col items-end min-w-[80px]">
        <span className={`text-xs ${ui.muted}`}>Precio</span>
        <span className={`font-bold tabular-nums ${brand.purpleText}`}>
          {fmtMoney(String(p.price))}
        </span>
      </div>

      {/* Stock */}
      <div className="text-right flex flex-col items-end min-w-[70px]">
        <span className={`text-xs ${ui.muted}`}>Stock</span>
        <span className={`font-bold tabular-nums ${lowStock ? 'text-rose-600 dark:text-rose-400' : 'text-slate-900 dark:text-slate-100'}`}>
          {stock}
        </span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1.5 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={onStock}
          title="Ajustar stock"
          className="w-9 h-9 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-100 dark:hover:bg-emerald-900/30 flex items-center justify-center transition-colors"
        >
          <i className="fa-solid fa-plus-minus text-sm" />
        </button>
        <button
          onClick={onEdit}
          title="Editar"
          className="w-9 h-9 rounded-lg bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-400 hover:bg-purple-100 dark:hover:bg-purple-900/30 flex items-center justify-center transition-colors"
        >
          <i className="fa-solid fa-pen text-sm" />
        </button>
      </div>
    </li>
  )
}

// ─── Product ficha modal (read-only detail card) ──────────────────────────────

interface FichaProps {
  product: ProductRow
  onClose: () => void
  onEdit: () => void
  onAdjustStock: () => void
}

function ProductFichaModal({ product: p, onClose, onEdit, onAdjustStock }: FichaProps) {
  const stock = Number(p.stock_total ?? p.stock ?? 0)
  return (
    <Modal title="Detalle del producto" onClose={onClose} size="xl">
      <div className="flex gap-4 mb-5">
        <div className="w-48 h-48 rounded-2xl bg-stone-100 dark:bg-slate-800 flex items-center justify-center overflow-hidden flex-shrink-0">
          {p.image_url ? (
            <img src={p.image_url} alt="" className="w-full h-full object-cover" />
          ) : (
            <i className="fa-solid fa-box text-slate-400 text-5xl" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-1">{p.label}</h2>
          <p className={`text-xs font-mono ${ui.muted} mb-3`}>{p.sku}{p.barcode ? ` · ${p.barcode}` : ''}</p>
          {p.description && <p className={`text-sm ${ui.muted} mb-3`}>{p.description}</p>}
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div><span className={ui.muted}>Departamento:</span> <span className="font-semibold">{p.department?.name ?? '—'}</span></div>
            <div><span className={ui.muted}>Marca:</span> <span className="font-semibold">{p.brand_name ?? '—'}</span></div>
            <div><span className={ui.muted}>Stock:</span> <span className={`font-bold ${stock <= (p.min_stock ?? 0) ? 'text-rose-600 dark:text-rose-400' : 'text-slate-900 dark:text-slate-100'}`}>{stock}</span></div>
            <div><span className={ui.muted}>Mínimo:</span> <span className="font-semibold">{p.min_stock ?? 0}</span></div>
          </div>
        </div>
      </div>

      <section className={`${ui.card} p-4 mb-3`}>
        <SectionHeader icon="fa-money-bill" label="Precios" accentColor="purple" />
        <div className="grid grid-cols-2 gap-2 mb-2">
          <div className="text-sm">
            <span className={ui.muted}>Base:</span>
            <span className="font-bold ml-2 tabular-nums">{fmtMoney(String(p.price ?? 0))}</span>
          </div>
          {p.cost != null && (
            <div className="text-sm">
              <span className={ui.muted}>Costo:</span>
              <span className="font-bold ml-2 tabular-nums">{fmtMoney(String(p.cost))}</span>
            </div>
          )}
        </div>
        {p.prices && p.prices.length > 0 && (
          <div className="space-y-1.5 mt-2">
            {p.prices.map((tier, i) => {
              const s = tierStyle(i)
              return (
                <div key={tier.id ?? i} className={`rounded-xl border ${s.border} ${s.bg} p-2 flex items-center gap-2 text-xs`}>
                  <i className={`fa-solid ${s.icon} ${s.text}`} />
                  <span className={`flex-1 font-bold ${s.text}`}>{tier.price_name}</span>
                  <span className={`tabular-nums ${ui.muted}`}>min {tier.min_quantity}</span>
                  <span className={`tabular-nums font-bold ${s.text}`}>{fmtMoney(String(tier.unit_price))}</span>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {p.packaging_units && p.packaging_units.length > 0 && (
        <section className={`${ui.card} p-4 mb-3`}>
          <SectionHeader icon="fa-box-open" label="Empaques" accentColor="blue" />
          <div className="space-y-1.5">
            {p.packaging_units.map((u, i) => (
              <div key={u.id ?? i} className="rounded-xl border border-blue-500/30 bg-blue-500/10 p-2 flex items-center gap-2 text-xs">
                <i className="fa-solid fa-box-open text-blue-700 dark:text-blue-300" />
                <span className="flex-1 font-bold text-blue-700 dark:text-blue-300">{u.name}</span>
                <span className={`tabular-nums ${ui.muted}`}>{u.units_per_package}u/caja</span>
                <span className="tabular-nums font-bold text-blue-700 dark:text-blue-300">{fmtMoney(String(u.package_price))}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="flex gap-2 mt-4">
        <button onClick={onClose} className={`${ui.btnSecondary} flex-1`}>Cerrar</button>
        <button onClick={onAdjustStock} className={`${ui.btnSecondary} flex-1`}>
          <i className="fa-solid fa-plus-minus" /> Ajustar stock
        </button>
        <button onClick={onEdit} className={`${ui.btnPrimary} flex-1`}>
          <i className="fa-solid fa-pen" /> Editar
        </button>
      </div>
    </Modal>
  )
}

// ─── Stock adjust modal ───────────────────────────────────────────────────────

interface StockModalProps {
  product: ProductRow
  onClose: () => void
  onSaved: () => void
}

function StockAdjustModal({ product, onClose, onSaved }: StockModalProps) {
  const { user } = useAuthStore()
  const [direction, setDirection] = useState<'IN' | 'OUT'>('IN')
  const [qty, setQty] = useState('')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)

  const variantId = product.variant_id
  const stock = Number(product.stock_total ?? product.stock ?? 0)

  async function submit() {
    if (!variantId) { toast.error('Producto sin variante'); return }
    if (!user?.branch_id) { toast.error('Sin sucursal asignada'); return }
    const qNum = parseFloat(qty)
    if (isNaN(qNum) || qNum <= 0) { toast.error('Cantidad inválida'); return }
    if (!reason.trim()) { toast.error('Motivo requerido'); return }

    const signed = direction === 'IN' ? qNum : -qNum
    if (direction === 'OUT' && qNum > stock) {
      toast.error(`Stock insuficiente. Disponible: ${stock}`)
      return
    }

    setSaving(true)
    try {
      await inventoryApi.createAdjustment({
        variant_id: variantId,
        quantity: signed,
        branch_id: user.branch_id,
        reason: reason.trim(),
      })
      toast.success(direction === 'IN' ? 'Stock agregado' : 'Stock retirado')
      onSaved()
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'No se pudo ajustar el stock')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal onClose={onClose} title="Ajustar stock">
      <div className="mb-4">
        <p className="text-sm text-slate-700 dark:text-slate-200 font-semibold">{product.label}</p>
        <p className="text-xs text-slate-500 dark:text-slate-400 font-mono">{product.sku} · Stock actual: <b>{stock}</b></p>
      </div>

      <div className="flex gap-2 mb-4">
        {(['IN', 'OUT'] as const).map((d) => (
          <button
            key={d}
            onClick={() => setDirection(d)}
            className={`flex-1 py-3 rounded-xl text-sm font-bold transition-colors ${
              direction === d
                ? d === 'IN'
                  ? 'bg-emerald-600 text-white'
                  : 'bg-rose-600 text-white'
                : 'bg-stone-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300'
            }`}
          >
            <i className={`fa-solid ${d === 'IN' ? 'fa-arrow-down' : 'fa-arrow-up'} mr-2`} />
            {d === 'IN' ? 'Entrada' : 'Salida'}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        <Field label="Cantidad">
          <input className={ui.input} type="number" min="0" step="1" value={qty} onChange={(e) => setQty(e.target.value)} autoFocus />
        </Field>
        <Field label="Motivo">
          <input
            className={ui.input}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={direction === 'IN' ? 'Ej. Recepción de proveedor' : 'Ej. Merma, rotura'}
          />
        </Field>
      </div>

      <div className="flex gap-2 mt-6">
        <button onClick={onClose} className={`${ui.btnSecondary} flex-1`} disabled={saving}>Cancelar</button>
        <button onClick={submit} disabled={saving} className={`${ui.btnPrimary} flex-1`}>
          {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Confirmar</>}
        </button>
      </div>
    </Modal>
  )
}

// ─── Reusable Modal shell ─────────────────────────────────────────────────────

function Modal({ title, onClose, children, size = 'md' }: { title: string; onClose: () => void; children: React.ReactNode; size?: 'md' | 'xl' }) {
  const widthClass = size === 'xl' ? 'max-w-2xl' : 'max-w-md'
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className={`${ui.card} w-full ${widthClass} p-6 max-h-[90vh] overflow-y-auto`}>
        <div className="flex items-center justify-between mb-4 sticky top-0 bg-white dark:bg-slate-900 z-10 pb-2">
          <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 p-1" aria-label="Cerrar">
            <i className="fa-solid fa-xmark text-lg" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

// ─── Import Excel modal ───────────────────────────────────────────────────────

interface ImportModalProps {
  onClose: () => void
  onDone: () => void
}

function ImportExcelModal({ onClose, onDone }: ImportModalProps) {
  type Step = 'upload' | 'preview' | 'result'
  const [step, setStep] = useState<Step>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [dryRun, setDryRun] = useState(false)
  const [preview, setPreview] = useState<UploadPreviewResponse | null>(null)
  const [result, setResult] = useState<{ created: number; updated: number; failed: number; errors: string[] } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function fetchPreview() {
    if (!file) return
    setLoading(true); setError(null)
    try {
      const res = await productsApi.uploadProducts(file, 'branch', undefined, { dryRun: true })
      setPreview(res as UploadPreviewResponse)
      setStep('preview')
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Error al analizar el archivo.')
    } finally {
      setLoading(false)
    }
  }

  async function commit() {
    if (!file) return
    if (dryRun) {
      // Simulation only — close without writing
      onClose()
      return
    }
    setLoading(true); setError(null)
    try {
      const res = await productsApi.uploadProducts(file, 'branch', undefined, { dryRun: false })
      setResult(res as { created: number; updated: number; failed: number; errors: string[] })
      setStep('result')
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Error al importar.')
    } finally {
      setLoading(false)
    }
  }

  function downloadErrorsCsv(errors: string[]) {
    const csv = ['error', ...errors].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `import-errors-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Modal title="Importar productos desde Excel" onClose={onClose} size="xl">
      {step === 'upload' && (
        <>
          <p className={`text-sm ${ui.muted} mb-4`}>
            Sube tu archivo Excel/CSV. En el siguiente paso verás qué se va a crear, actualizar o omitir antes de aplicar.
          </p>
          <Field label="Archivo">
            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className={ui.input}
            />
          </Field>
          <label className="flex items-center gap-2 mt-3 text-xs text-slate-600 dark:text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              className="rounded"
            />
            Solo simular (no aplicar cambios)
          </label>
          {error && <p className="text-sm text-rose-600 dark:text-rose-400 mt-3">{error}</p>}
          <div className="flex gap-2 mt-6">
            <button onClick={onClose} className={`${ui.btnSecondary} flex-1`} disabled={loading}>Cancelar</button>
            <button onClick={fetchPreview} disabled={loading || !file} className={`${ui.btnPrimary} flex-1`}>
              {loading ? <i className="fa-solid fa-spinner fa-spin" /> : <>Continuar <i className="fa-solid fa-arrow-right" /></>}
            </button>
          </div>
        </>
      )}

      {step === 'preview' && preview && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4 text-sm">
            <div className={`${ui.card} p-3`}>
              <p className={ui.kpiLabel}>Filas</p>
              <p className="text-xl font-bold tabular-nums">{preview.total_rows}</p>
            </div>
            <div className={`${ui.card} p-3`}>
              <p className={ui.kpiLabel}>Nuevos</p>
              <p className="text-xl font-bold text-emerald-600 dark:text-emerald-400 tabular-nums">{preview.to_create}</p>
            </div>
            <div className={`${ui.card} p-3`}>
              <p className={ui.kpiLabel}>Actualizar</p>
              <p className="text-xl font-bold text-purple-600 dark:text-purple-400 tabular-nums">{preview.to_update}</p>
            </div>
            <div className={`${ui.card} p-3`}>
              <p className={ui.kpiLabel}>Errores</p>
              <p className="text-xl font-bold text-rose-600 dark:text-rose-400 tabular-nums">{preview.errors}</p>
            </div>
          </div>

          {preview.preview.length > 0 && (
            <div className={`${ui.card} p-3 mb-4`}>
              <TablaDesplazable className="max-h-64 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-white dark:bg-slate-900">
                    <tr>
                      <th className="text-left">Acción</th>
                      <th className="text-left">SKU</th>
                      <th className="text-left">Nombre</th>
                      <th className="text-right">Precio</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.preview.map((r, i) => (
                      <tr key={i} className="border-t border-stone-100 dark:border-slate-800">
                        <td>
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            r.action === 'NEW' ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400' :
                            r.action === 'UPDATE' ? 'bg-purple-500/15 text-purple-700 dark:text-purple-400' :
                            'bg-rose-500/15 text-rose-700 dark:text-rose-400'
                          }`}>
                            {r.action === 'NEW' ? 'NUEVO' : r.action === 'UPDATE' ? 'ACTUALIZA' : 'ERROR'}
                          </span>
                        </td>
                        <td className="font-mono">{r.sku ?? '—'}</td>
                        <td>{r.name ?? r.error_message ?? '—'}</td>
                        <td className="text-right tabular-nums">{r.price != null ? fmtMoney(String(r.price)) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TablaDesplazable>
              {preview.total_rows > 20 && (
                <p className={`text-xs ${ui.muted} mt-2 text-center`}>
                  Mostrando 20 de {preview.total_rows} filas. Se aplicará a todas.
                </p>
              )}
            </div>
          )}

          {error && <p className="text-sm text-rose-600 dark:text-rose-400 mb-3">{error}</p>}

          <div className="flex gap-2 mt-4">
            <button onClick={() => setStep('upload')} className={`${ui.btnSecondary} flex-1`} disabled={loading}>
              <i className="fa-solid fa-arrow-left" /> Atrás
            </button>
            <button
              onClick={commit}
              disabled={loading || (!dryRun && preview.to_create + preview.to_update === 0)}
              className={`${ui.btnPrimary} flex-1`}
            >
              {loading ? <i className="fa-solid fa-spinner fa-spin" /> :
                dryRun ? 'Cerrar simulación' :
                <><i className="fa-solid fa-check" /> Aplicar {preview.to_create + preview.to_update} cambios</>
              }
            </button>
          </div>
        </>
      )}

      {step === 'result' && result && (
        <>
          <div className="space-y-2 text-sm mb-4">
            <div className="flex justify-between"><span className={ui.muted}>Creados</span><span className="font-bold text-emerald-600 dark:text-emerald-400">{result.created}</span></div>
            <div className="flex justify-between"><span className={ui.muted}>Actualizados</span><span className="font-bold text-purple-600 dark:text-purple-400">{result.updated}</span></div>
            <div className="flex justify-between"><span className={ui.muted}>Fallidos</span><span className="font-bold text-rose-600 dark:text-rose-400">{result.failed}</span></div>
          </div>
          {result.errors.length > 0 && (
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1">
                <p className={ui.kpiLabel}>Errores</p>
                <button onClick={() => downloadErrorsCsv(result.errors)} className="text-xs text-purple-600 hover:text-purple-700">
                  <i className="fa-solid fa-file-csv mr-1" /> Descargar CSV
                </button>
              </div>
              <ul className="text-xs text-rose-600 dark:text-rose-400 max-h-32 overflow-y-auto space-y-1">
                {result.errors.slice(0, 20).map((err, i) => <li key={i}>{err}</li>)}
              </ul>
            </div>
          )}
          <button
            onClick={() => {
              if (result && (result.created > 0 || result.updated > 0)) {
                onDone()
              } else {
                onClose()
              }
            }}
            className={`${ui.btnPrimary} w-full`}
          >
            Cerrar
          </button>
        </>
      )}
    </Modal>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className={`block ${ui.kpiLabel} mb-1`}>{label}</span>
      {children}
    </label>
  )
}
