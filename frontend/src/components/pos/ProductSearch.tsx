import { useState, useCallback, useRef, useEffect } from 'react'
import { productsApi } from '../../api/products'
import { usePOSStore } from '../../store/posStore'
import { useAuthStore } from '../../store/authStore'
import type { Product, ProductVariant } from '../../types/products'
import { ProductDetailModal } from './modals/ProductDetailModal'
import { VariantPickerModal } from './modals/VariantPickerModal'
import { needsPicker, pickVariantForCart, variantShortLabel } from './variantPicker'
import { formatCurrency } from '../../utils/currency'
import { useExchangeRateStore } from '../../store/exchangeRateStore'
import { formatUsd, usdEquivalent } from '../../utils/usd'

const EDIT_ROLES = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO']

type SortOrder = 'best_sellers' | 'name_asc' | 'price_asc' | 'price_desc'
const SORT_STORAGE_KEY = 'pos.sortBy'
const DEFAULT_SORT: SortOrder = 'best_sellers'

type TierView = {
  label: string
  name: string
  value: number
  color: string
  bg: string
  border: string
}

// Paleta extensible — cicla si el producto tiene más precios que colores.
const TIER_PALETTE: Array<Omit<TierView, 'label' | 'name' | 'value'>> = [
  { color: '#047857', bg: 'rgba(16,185,129,0.10)', border: 'rgba(16,185,129,0.35)' },   // emerald
  { color: '#b45309', bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.40)' },   // amber
  { color: '#6d28d9', bg: 'rgba(139,92,246,0.10)', border: 'rgba(139,92,246,0.40)' },   // violet
  { color: '#0e7490', bg: 'rgba(6,182,212,0.10)',  border: 'rgba(6,182,212,0.40)'  },   // cyan
  { color: '#be185d', bg: 'rgba(236,72,153,0.10)', border: 'rgba(236,72,153,0.40)' },   // pink
  { color: '#4338ca', bg: 'rgba(99,102,241,0.10)', border: 'rgba(99,102,241,0.40)' },   // indigo
]

// Etiquetas fijas por posición en la card — independientes del price_name del backend.
// Slot 0 = Menudeo (base), 1 = Mayoreo, 2 = Caja. Slot 3+ usa el nombre del tier o P{i+1}.
const SLOT_LABELS = ['Menudeo', 'Mayoreo', 'Caja']

function buildTierDisplay(p: Product, basePrice: number): TierView[] {
  const raw = (p.prices ?? [])
    .filter(t => Number(t.unit_price) > 0)
    .map(t => ({ name: t.price_name, value: Number(t.unit_price), min: t.min_quantity ?? 1 }))
    .sort((a, b) => a.min - b.min)

  // Siempre incluir el precio base como primer slot.
  const merged: Array<{ name: string; value: number }> = []
  if (basePrice > 0) merged.push({ name: 'Menudeo', value: basePrice })

  // Añadir tiers, omitiendo los que sean exactamente iguales al base para evitar duplicados.
  for (const t of raw) {
    if (Math.abs(t.value - basePrice) < 0.01 && t.min <= 1) continue
    merged.push({ name: t.name || 'Precio', value: t.value })
  }

  return merged.map((t, i) => ({
    label: SLOT_LABELS[i] ?? (t.name || `P${i + 1}`),
    name: t.name,
    value: t.value,
    ...TIER_PALETTE[i % TIER_PALETTE.length],
  }))
}

interface ProductSearchProps {
  refreshKey?: number
}

export function ProductSearch({ refreshKey = 0 }: ProductSearchProps = {}) {
  const addItem = usePOSStore((s) => s.addItem)
  const cart   = usePOSStore((s) => s.cart)
  // Precio en dólares por tarjeta. Solo lectura: POS.tsx dispara la carga.
  const usdRate = useExchangeRateStore((s) => s.rate)
  const { user } = useAuthStore()
  const canEdit = !!user?.role && EDIT_ROLES.includes(user.role)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Product[]>([])
  const [loading, setLoading] = useState(false)
  const [defaultResults, setDefaultResults] = useState<Product[]>([])
  const [defaultLoading, setDefaultLoading] = useState(true)
  const [detailProduct, setDetailProduct] = useState<Product | null>(null)
  const [pickerFor, setPickerFor] = useState<Product | null>(null)
  const [limitId, setLimitId] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<SortOrder>(() => {
    try {
      const v = localStorage.getItem(SORT_STORAGE_KEY) as SortOrder | null
      return v === 'best_sellers' || v === 'name_asc' || v === 'price_asc' || v === 'price_desc' ? v : DEFAULT_SORT
    } catch { return DEFAULT_SORT }
  })
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastInputAtRef = useRef<number>(0)
  const lastSearchTargetRef = useRef<string>('')
  const resultsRef = useRef<Product[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  // El escáner teclea sobre el input: si un clic en un resultado se lleva el
  // foco, el siguiente código de barras se pierde. Se devuelve en el frame
  // siguiente, ya con el DOM de resultados actualizado.
  const devolverFoco = () => requestAnimationFrame(() => inputRef.current?.focus())

  useEffect(() => { resultsRef.current = results }, [results])

  useEffect(() => {
    try { localStorage.setItem(SORT_STORAGE_KEY, sortBy) } catch {}
  }, [sortBy])

  // Cargar grid inicial al montar y al cambiar sortBy o refreshKey
  useEffect(() => {
    let cancelled = false
    setDefaultLoading(true)
    productsApi.posSearch('', sortBy).then((data) => {
      if (!cancelled) { setDefaultResults(data); setDefaultLoading(false) }
    }).catch(() => {
      if (!cancelled) setDefaultLoading(false)
    })
    return () => { cancelled = true }
  }, [sortBy, refreshKey])

  const search = useCallback(async (q: string): Promise<Product[]> => {
    lastSearchTargetRef.current = q
    if (!q.trim()) { setResults([]); return [] }
    setLoading(true)
    try {
      const data = await productsApi.posSearch(q, sortBy)
      setResults(data)
      return data
    } catch {
      setResults([])
      return []
    } finally {
      setLoading(false)
    }
  }, [sortBy])

  const handleChange = (val: string) => {
    setQuery(val)
    const now = Date.now()
    const delta = now - lastInputAtRef.current
    const prevTarget = lastSearchTargetRef.current
    lastInputAtRef.current = now

    if (debounceRef.current) clearTimeout(debounceRef.current)

    // HID barcode scanner heuristic: rapid keystroke burst (<50ms apart) that
    // injects 8+ chars in one shot vs last issued search target.
    const isScannerBurst =
      delta < 50 &&
      val.length - prevTarget.length >= 8
    const debounceMs = isScannerBurst ? 30 : 300

    debounceRef.current = setTimeout(() => search(val), debounceMs)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return
    e.preventDefault()
    const val = query
    if (debounceRef.current) { clearTimeout(debounceRef.current); debounceRef.current = null }
    // If the current displayed results already match this query and there is
    // exactly one, auto-add. Otherwise run the search immediately; cajero can
    // confirm again on the fresh result set.
    if (val.trim() && lastSearchTargetRef.current === val && resultsRef.current.length === 1) {
      addOrPick(resultsRef.current[0])
      return
    }
    search(val).then((data) => {
      if (lastSearchTargetRef.current === val && data.length === 1) {
        addOrPick(data[0])
      }
    })
  }

  // Cuenta por variante cuando la hay: dos tallas del mismo producto no
  // comparten existencia, y sumarlas bloqueaba la segunda talla al llegar al
  // stock de la primera.
  const cartQtyUnits = (productId: string, variantId?: string | null): number => {
    let total = 0
    for (const c of cart) {
      if (c.product_id !== productId) continue
      if (variantId && c.variant_id && c.variant_id !== variantId) continue
      if (c.cart_key?.includes('::caja::')) {
        const cajaTier = c.prices?.find(p => p.price_name.toLowerCase().includes('caja'))
        total += c.quantity * (cajaTier?.min_quantity ?? 1)
      } else {
        total += c.quantity
      }
    }
    return total
  }

  // `picked` es la variante que el cajero eligió en el modal. Se recibe entera
  // porque el producto del resultado de búsqueda puede traer la colección de
  // variantes incompleta: rebuscarla en `p.variants` dejaba la línea sin talla.
  const addToCart = (p: Product, picked?: ProductVariant) => {
    const variantId = picked?.id ?? p.matched_variant_id ?? p.variants?.[0]?.id ?? undefined
    const variant = picked ?? p.variants?.find((v) => v.id === variantId)
    const label = (variant ? variantShortLabel(variant) : null) ?? undefined
    const stock = Number(p.stock_total ?? 0)
    if (stock > 0 && cartQtyUnits(p.id, variantId) >= stock) {
      setLimitId(p.id)
      setTimeout(() => setLimitId(null), 2000)
      return
    }
    addItem({
      product_id: p.id,
      ...(variantId ? { variant_id: variantId, cart_key: variantId } : {}),
      ...(label ? { variant_label: label } : {}),
      base_price: Number(p.price),
      sku: p.sku ?? '',
      // Nombre de VENTA: el mismo texto que va a salir en el ticket
      // ("Louis Vuitton · Chamarra mezclilla · Talla M"). Sin marca ni modelo
      // es el de siempre ("Playera (M)"), así que nada cambia para el resto.
      name: variant?.sale_name
        ?? (label ? `${p.sale_name ?? p.name} (${label})` : (p.sale_name ?? p.name)),
      price: Number(p.price),
      quantity: 1,
      discount: 0,
      subtotal: Number(p.price),
      stock,
      prices: p.prices?.map(pr => ({
        id: String(pr.id),
        price_name: pr.price_name,
        min_quantity: pr.min_quantity,
        unit_price: Number(pr.unit_price),
        linked_package_id: pr.linked_package_id ?? null,
      })),
      packaging_units: p.packaging_units?.map(pk => ({
        id: String(pk.id),
        name: pk.name,
        barcode: pk.barcode,
        units_per_package: Number(pk.units_per_package),
        package_price: Number(pk.package_price),
      })),
    })
    setQuery('')
    setResults([])
    devolverFoco()
  }

  const addOrPick = (p: Product) => {
    if (needsPicker(p)) { setPickerFor(p); return }
    addToCart(p)
  }

  const stockNum = (p: Product) => Number(p.stock_total ?? 0)

  // Qué lista mostrar según si hay búsqueda activa
  const displayResults = query.trim() ? results : defaultResults
  const isLoadingDisplay = query.trim() ? loading : defaultLoading

  return (
    <div className="flex flex-col h-full">
      {/* Search input + sort */}
      <div className="p-3 flex items-center gap-2" style={{ borderBottom: '1px solid var(--dax-border-dim)' }}>
        <div className="relative flex-1">
          <i className="fa-solid fa-search absolute left-3 top-1/2 -translate-y-1/2 text-sm" style={{ color: 'var(--dax-text-faint)' }} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => handleChange(e.target.value)}
            onKeyDown={handleKeyDown}
            className="dax-input pl-9 w-full"
            placeholder="Buscar por nombre o SKU..."
            autoFocus
          />
          {loading && (
            <i className="fa-solid fa-spinner fa-spin absolute right-3 top-1/2 -translate-y-1/2 text-sm" style={{ color: 'var(--dax-text-faint)' }} />
          )}
        </div>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as SortOrder)}
          className="dax-input text-xs font-semibold flex-shrink-0"
          style={{ maxWidth: 160 }}
          title="Orden de productos"
        >
          <option value="best_sellers">Más vendidos</option>
          <option value="name_asc">A-Z</option>
          <option value="price_asc">Precio ↑</option>
          <option value="price_desc">Precio ↓</option>
        </select>
      </div>

      {/* Results grid */}
      <div className="flex-1 overflow-y-auto p-3">

        {/* Título contextual cuando no hay búsqueda */}
        {!query.trim() && displayResults.length > 0 && (
          <p className="text-[10px] font-bold uppercase tracking-widest mb-2 px-1"
             style={{ color: 'var(--dax-text-faint)' }}>
            Todos los productos
          </p>
        )}

        {/* Spinner de carga inicial */}
        {isLoadingDisplay && displayResults.length === 0 && (
          <div className="flex justify-center py-16">
            <i className="fa-solid fa-spinner fa-spin text-2xl" style={{ color: 'var(--dax-text-faint)' }} />
          </div>
        )}

        {/* Estado vacío */}
        {displayResults.length === 0 && !isLoadingDisplay && (
          <div className="text-center py-16">
            <i className="fa-solid fa-barcode text-4xl mb-3 block" style={{ color: 'var(--dax-text-faint)' }} />
            <p className="text-sm" style={{ color: 'var(--dax-text-muted)' }}>
              {query.trim() ? 'Sin resultados' : 'No hay productos disponibles'}
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 gap-2">
          {displayResults.map((p) => {
            const matched = p.variants?.find((v) => v.id === p.matched_variant_id)
            const stock = (p.variants?.length ?? 0) > 1
              ? (matched ? Number(matched.stock_total ?? 0) : p.variants!.reduce((a, v) => a + Number(v.stock_total ?? 0), 0))
              : stockNum(p)
            const price = Number(p.price)
            const inCart = cartQtyUnits(p.id, p.matched_variant_id)
            const atLimit = stock > 0 && inCart >= stock
            const isLimit = limitId === p.id
            const isInCart = inCart > 0
            const tiers = buildTierDisplay(p, price)
            return (
              <div
                key={p.id}
                className="flex flex-col gap-1.5 rounded-2xl p-3 transition-shadow hover:shadow-md"
                style={{
                  background: 'var(--dax-surface)',
                  border: `1.5px solid ${isInCart ? 'rgba(139,92,246,0.55)' : 'var(--dax-border-dim)'}`,
                  boxShadow: isInCart ? '0 0 0 2px rgba(139,92,246,0.18)' : undefined,
                }}
              >
                <button
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => addOrPick(p)}
                  disabled={stock <= 0 || atLimit}
                  className={`text-left flex flex-col gap-1.5 group w-full disabled:opacity-40 disabled:cursor-not-allowed transition-colors ${isLimit ? 'opacity-80' : ''}`}
                >
                  {/* Image / icon */}
                  <div
                    className="w-full aspect-square rounded-xl overflow-hidden flex items-center justify-center"
                    style={{ background: p.image_url ? undefined : 'var(--dax-elevated)' }}
                  >
                    {p.image_url ? (
                      <img src={p.image_url} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <i className="fa-solid fa-box text-2xl" style={{ color: 'var(--dax-text-faint)' }} />
                    )}
                  </div>
                  <p className="text-sm font-bold leading-snug line-clamp-2"
                     style={{ color: 'var(--dax-text)', lineHeight: '1.25' }}>
                    {p.sale_name ?? p.name}
                  </p>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] font-mono truncate" style={{ color: 'var(--dax-text-faint)' }}>{p.sku}</p>
                    {(p.variants?.length ?? 0) > 1 && (
                      <span
                        className="text-[9px] font-bold px-1.5 py-0.5 rounded flex-shrink-0"
                        style={{ background: 'rgba(99,102,241,0.15)', color: '#4338ca' }}
                      >
                        {p.variants!.length} variantes
                      </span>
                    )}
                    {p.has_iva && (
                      <span
                        className="text-[9px] font-bold px-1.5 py-0.5 rounded flex-shrink-0"
                        style={{ background: 'rgba(245,158,11,0.18)', color: '#b45309' }}
                      >
                        IVA
                      </span>
                    )}
                  </div>

                  {/* Precios — base en línea completa, tiers extra en fila debajo */}
                  {tiers.length > 0 && (
                    <div className="flex flex-col gap-1 pt-1">
                      {/* Precio base (Menudeo) — prominente, full width */}
                      <div
                        className="rounded-lg px-2 py-1.5 flex items-center justify-between gap-2"
                        style={{ background: tiers[0].bg, border: `1px solid ${tiers[0].border}` }}
                        title={tiers[0].name}
                      >
                        <span className="text-[10px] font-bold uppercase tracking-wider"
                              style={{ color: tiers[0].color }}>
                          {tiers[0].label}
                        </span>
                        <span className="text-base font-black tabular-nums whitespace-nowrap"
                              style={{ color: tiers[0].color }}>
                          {formatCurrency(tiers[0].value)}
                        </span>
                      </div>

                      {usdRate !== null && (
                        <p
                          className="text-[10px] font-semibold tabular-nums text-right"
                          style={{ color: 'var(--dax-text-faint)' }}
                        >
                          ≈ {formatUsd(usdEquivalent(tiers[0].value, usdRate))}
                        </p>
                      )}

                      {/* Tiers extra (Mayoreo, Caja, …) — fila compacta debajo */}
                      {tiers.length > 1 && (
                        <div
                          className="grid gap-1"
                          style={{ gridTemplateColumns: `repeat(${Math.min(tiers.length - 1, 3)}, minmax(0, 1fr))` }}
                        >
                          {tiers.slice(1).map((t, i) => (
                            <div
                              key={i}
                              className="rounded-md px-1.5 py-1 flex flex-col items-center justify-center"
                              style={{ background: t.bg, border: `1px solid ${t.border}` }}
                              title={t.name}
                            >
                              <span className="text-[9px] font-bold uppercase tracking-wider leading-none"
                                    style={{ color: t.color }}>
                                {t.label}
                              </span>
                              <span className="text-xs font-black tabular-nums leading-tight mt-0.5 whitespace-nowrap truncate block w-full text-center"
                                    style={{ color: t.color }}>
                                {formatCurrency(t.value)}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="flex items-end justify-end mt-auto pt-1">
                    {isLimit ? (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-600/20 text-red-600">
                        Límite
                      </span>
                    ) : (
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${stock > 0 ? 'bg-emerald-600/20 text-emerald-700' : 'bg-red-600/20 text-red-600'}`}>
                        {stock > 0 ? `${stock} stock` : 'Sin stock'}
                      </span>
                    )}
                  </div>
                </button>
                <button
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={(e) => { e.stopPropagation(); setDetailProduct(p) }}
                  className="w-full mt-1 py-1.5 text-xs font-semibold rounded-xl border transition-colors"
                  style={{ borderColor: 'var(--dax-border)', color: 'var(--dax-text-muted)' }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(139,92,246,0.08)' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                  title="Ver detalles"
                >
                  <i className="fa-solid fa-circle-info mr-1.5" /> Ver detalles
                </button>
              </div>
            )
          })}
        </div>
      </div>

      <ProductDetailModal
        product={detailProduct}
        onClose={() => { setDetailProduct(null); devolverFoco() }}
        onAddToCart={(p) => { addToCart(p); setDetailProduct(null) }}
        canEdit={canEdit}
        onSaved={() => {
          productsApi.posSearch('', sortBy).then(setDefaultResults).catch(() => {})
          if (query.trim()) search(query)
        }}
      />

      {pickerFor && (
        <VariantPickerModal
          product={pickerFor}
          onPick={(v) => { addToCart(pickVariantForCart(pickerFor, v), v); setPickerFor(null) }}
          onClose={() => { setPickerFor(null); devolverFoco() }}
        />
      )}
    </div>
  )
}
