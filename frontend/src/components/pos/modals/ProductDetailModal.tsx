import { useEffect, useMemo, useRef, useState } from 'react'
import type { Product, Brand, Department, PackagingUnit } from '../../../types/products'
import { formatCurrency } from '../../../utils/currency'
import { sortByName } from '../../../utils/sortByName'
import { productsApi } from '../../../api/products'
import { inventoryApi } from '../../../api/inventory'
import { useAuthStore } from '../../../store/authStore'
import { variantAxisLabel, variantDisplayName, variantShortLabel } from '../variantPicker'

interface PackRow {
  id?: string
  name: string
  barcode: string
  units_per_package: string
  package_price: string
}

type Mode = 'view' | 'create'

interface Props {
  product: Product | null
  mode?: Mode
  onClose: () => void
  onAddToCart?: (product: Product) => void
  onSaved?: (product: Product) => void
  canEdit?: boolean
}

type TierSlot = {
  price_name: string
  min_quantity: number
  unit_price: string
  color: string
  bg: string
  border: string
  label: string
}

// Paleta cíclica — acomoda cualquier cantidad de precios.
const TIER_PALETTE: Array<{ color: string; bg: string; border: string }> = [
  { color: '#047857', bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.40)' },  // emerald
  { color: '#b45309', bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.45)' },  // amber
  { color: '#6d28d9', bg: 'rgba(139,92,246,0.08)',  border: 'rgba(139,92,246,0.45)' },  // violet
  { color: '#0e7490', bg: 'rgba(6,182,212,0.08)',   border: 'rgba(6,182,212,0.40)'  },  // cyan
  { color: '#be185d', bg: 'rgba(236,72,153,0.08)',  border: 'rgba(236,72,153,0.40)' },  // pink
  { color: '#4338ca', bg: 'rgba(99,102,241,0.08)',  border: 'rgba(99,102,241,0.40)' },  // indigo
]

const paletteFor = (i: number) => TIER_PALETTE[i % TIER_PALETTE.length]

const DEFAULT_CREATE_TIERS: Array<{ name: string; min: number }> = [
  { name: 'Menudeo', min: 1  },
  { name: 'Mayoreo', min: 6  },
  { name: 'Caja',    min: 12 },
]

function initialTiers(product: Product | null, isCreate: boolean): TierSlot[] {
  const raw = (product?.prices ?? [])
    .slice()
    .sort((a, b) => (a.min_quantity ?? 1) - (b.min_quantity ?? 1))

  // Create mode: 3 slots default vacíos (Base + Mayoreo + Especial)
  if (isCreate && raw.length === 0) {
    return DEFAULT_CREATE_TIERS.map((d, i) => ({
      ...paletteFor(i),
      label: i === 0 ? 'Base' : `P${i} · ${d.name}`,
      price_name: d.name,
      min_quantity: d.min,
      unit_price: i === 0 && product?.price ? String(product.price) : '',
    }))
  }

  // View/edit: primer slot = precio base del producto; luego cada tier que difiera del base.
  const basePrice = Number(product?.price ?? 0)
  const slots: Array<{ price_name: string; min_quantity: number; unit_price: number }> = []
  if (basePrice > 0) {
    slots.push({ price_name: 'Base', min_quantity: 1, unit_price: basePrice })
  }
  const isBaseLikeName = (n: string | undefined) => {
    const s = (n || '').trim().toLowerCase()
    return s === 'base' || s === 'menudeo'
  }
  for (const t of raw) {
    const v = Number(t.unit_price ?? 0)
    const min = t.min_quantity ?? 1
    // Dedupe contra el slot sintético "Base" si coincide el nombre y min<=1,
    // independientemente de si los precios difieren — el usuario editó Base, ése es el canon.
    if (basePrice > 0 && min <= 1 && isBaseLikeName(t.price_name)) continue
    slots.push({ price_name: t.price_name || 'Precio', min_quantity: min, unit_price: v })
  }
  // Fallback: si no hay nada, un slot vacío de Base.
  if (slots.length === 0) {
    slots.push({ price_name: 'Base', min_quantity: 1, unit_price: 0 })
  }

  return slots.map((t, i) => ({
    ...paletteFor(i),
    label: i === 0 ? 'Base' : `P${i} · ${t.price_name}`,
    price_name: t.price_name,
    min_quantity: t.min_quantity,
    unit_price: String(t.unit_price),
  }))
}

const MetaCell = ({ label, value }: { label: string; value: string | number }) => (
  <div className="rounded-lg p-2.5" style={{ background: 'var(--dax-elevated)' }}>
    <p className="text-[10px]" style={{ color: 'var(--dax-text-faint)' }}>{label}</p>
    <p className="text-xs font-semibold mt-0.5" style={{ color: 'var(--dax-text)' }}>{String(value)}</p>
  </div>
)

export function ProductDetailModal({
  product,
  mode = 'view',
  onClose,
  onAddToCart,
  onSaved,
  canEdit = false,
}: Props) {
  // En mode=create renderizamos con product=null; en mode=view requiere product.
  const [editing, setEditing] = useState<boolean>(mode === 'create')
  const [saving, setSaving]   = useState(false)
  const [error, setError]     = useState<string | null>(null)

  // Form state
  const [name, setName]       = useState(product?.name ?? '')
  const [sku, setSku]         = useState(product?.sku ?? '')
  const [barcode, setBarcode] = useState(product?.barcode ?? '')
  const [cost, setCost]       = useState(String(product?.cost ?? ''))
  const [stock, setStock]     = useState(String(product?.stock_total ?? product?.stock ?? 0))
  const [desc, setDesc]       = useState(product?.description ?? '')
  const [imageUrl, setImage]  = useState(product?.image_url ?? '')
  const [tiers, setTiers]     = useState<TierSlot[]>(() => initialTiers(product ?? null, mode === 'create'))
  const [brandId, setBrandId]           = useState<string>(product?.brand_id ?? '')
  const [departmentId, setDepartmentId] = useState<string>(product?.department?.id ?? '')
  const [brands, setBrands]             = useState<Brand[]>([])
  const [departments, setDepartments]   = useState<Department[]>([])

  // Agregar al stock (solo edit mode, productos existentes con variant)
  const [addStockQty, setAddStockQty]       = useState('')
  const [addStockReason, setAddStockReason] = useState('')
  const [addStockBusy, setAddStockBusy]     = useState(false)
  const [addStockMsg, setAddStockMsg]       = useState<string | null>(null)
  // Variante elegida para el ajuste — con varias tallas, por omisión la que escaneó/matched.
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(
    product?.matched_variant_id ?? product?.variants?.[0]?.id ?? null
  )

  // Producto recargado tras un ajuste de stock. El `product` de arriba lo manda
  // el padre y no se entera del movimiento: sin esto, "Agregar 5" dejaba el
  // número en el mismo 12 de antes y el cajero volvía a agregarlas.
  const [refreshed, setRefreshed] = useState<Product | null>(null)
  const live = refreshed ?? product

  // Empaques (cajas)
  const [packs, setPacks] = useState<PackRow[]>([])
  // Foto: subida por archivo
  const [imgUploading, setImgUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setEditing(mode === 'create')
    setError(null)
    setName(product?.name ?? '')
    setSku(product?.sku ?? '')
    setBarcode(product?.barcode ?? '')
    setCost(String(product?.cost ?? ''))
    setStock(String(product?.stock_total ?? product?.stock ?? 0))
    setDesc(product?.description ?? '')
    setImage(product?.image_url ?? '')
    setTiers(initialTiers(product ?? null, mode === 'create'))
    setBrandId(product?.brand_id ?? '')
    setDepartmentId(product?.department?.id ?? '')
    setSelectedVariantId(product?.matched_variant_id ?? product?.variants?.[0]?.id ?? null)
    setRefreshed(null)
    setPacks(
      (product?.packaging_units ?? []).map((u: PackagingUnit) => ({
        id: u.id,
        name: u.name,
        barcode: u.barcode ?? '',
        units_per_package: String(u.units_per_package),
        package_price: String(u.package_price),
      }))
    )
  }, [product, mode])

  // Foto: subir archivo (solo productos existentes — el upload va por id)
  async function uploadImage(file: File) {
    if (!product) {
      setError('Crea el producto primero, luego sube la foto')
      return
    }
    setImgUploading(true)
    try {
      const updated = await productsApi.uploadImage(product.id, file)
      setImage(updated.image_url ?? '')
      onSaved?.(updated)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'No se pudo subir la foto')
    } finally {
      setImgUploading(false)
    }
  }

  async function deleteImage() {
    if (!product) return
    setImgUploading(true)
    try {
      const updated = await productsApi.deleteImage(product.id)
      setImage(updated.image_url ?? '')
      onSaved?.(updated)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'No se pudo eliminar la foto')
    } finally {
      setImgUploading(false)
    }
  }

  // La ficha se abre encima de todo y hasta ahora solo se cerraba con el botón
  // o clicando el fondo: con el teclado no había salida.
  const abierto = mode === 'create' || !!product
  const cardRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!abierto) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [abierto, onClose])

  // Foco inicial dentro del diálogo: sin esto el lector de pantalla y el
  // tabulador seguían navegando la pantalla de atrás.
  useEffect(() => {
    if (abierto) cardRef.current?.focus()
  }, [abierto, product?.id])

  // Cargar catálogos de marca/departamento al entrar en modo edición o creación.
  useEffect(() => {
    if (!editing) return
    let cancelled = false
    Promise.all([productsApi.getBrands(), productsApi.getDepartments()])
      .then(([bs, ds]) => {
        if (cancelled) return
        setBrands(sortByName(bs))
        setDepartments(sortByName(ds))
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [editing])

  const variantesVivas = live?.variants ?? []
  // Nombre de la talla que representa el número grande — nunca "Estándar".
  const nombreVariante = (() => {
    const v = variantesVivas.find(x => x.id === selectedVariantId)
    return v ? variantShortLabel(v) : null
  })()

  // Con varias tallas, "Stock actual" debe seguir a la variante elegida en el
  // selector, no quedarse pegado a la que matcheó el escaneo (o la primera).
  const selectedVariantStock = selectedVariantId
    ? variantesVivas.find(v => v.id === selectedVariantId)?.stock_total
    : undefined
  const displayStock = selectedVariantStock != null
    ? Number(selectedVariantStock)
    : Number(live?.stock_total ?? live?.stock ?? 0)
  const viewTiers = useMemo(() => {
    const raw = (product?.prices ?? [])
      .slice()
      .sort((a, b) => (a.min_quantity ?? 1) - (b.min_quantity ?? 1))
    const base = Number(product?.price ?? 0)
    const out: Array<{ key: string; name: string; min: number; value: number }> = []
    if (base > 0) out.push({ key: 'base', name: 'Base', min: 1, value: base })
    const isBaseLike = (n: string | undefined) => {
      const s = (n || '').trim().toLowerCase()
      return s === 'base' || s === 'menudeo'
    }
    for (const t of raw) {
      const v = Number(t.unit_price ?? 0)
      const min = t.min_quantity ?? 1
      if (base > 0 && min <= 1 && isBaseLike(t.price_name)) continue
      out.push({ key: String(t.id), name: t.price_name, min, value: v })
    }
    return out
  }, [product])

  if (mode === 'view' && !product) return null

  const cancelEdit = () => {
    if (mode === 'create') { onClose(); return }
    setEditing(false)
    setError(null)
    setName(product?.name ?? '')
    setSku(product?.sku ?? '')
    setBarcode(product?.barcode ?? '')
    setCost(String(product?.cost ?? ''))
    setStock(String(product?.stock_total ?? product?.stock ?? 0))
    setDesc(product?.description ?? '')
    setImage(product?.image_url ?? '')
    setTiers(initialTiers(product ?? null, false))
    setBrandId(product?.brand_id ?? '')
    setDepartmentId(product?.department?.id ?? '')
    setSelectedVariantId(product?.matched_variant_id ?? product?.variants?.[0]?.id ?? null)
  }

  const updateTier = (idx: number, patch: Partial<Pick<TierSlot, 'unit_price' | 'price_name' | 'min_quantity'>>) => {
    setTiers(prev => prev.map((t, i) => i === idx ? { ...t, ...patch } : t))
  }

  const bumpPrice = (idx: number, delta: number) => {
    setTiers(prev => prev.map((t, i) => {
      if (i !== idx) return t
      const current = Number(t.unit_price) || 0
      const next = Math.max(0, Math.round((current + delta) * 100) / 100)
      return { ...t, unit_price: next.toFixed(2) }
    }))
  }

  const bumpMin = (idx: number, delta: number) => {
    setTiers(prev => prev.map((t, i) => {
      if (i !== idx) return t
      const next = Math.max(1, (t.min_quantity || 1) + delta)
      return { ...t, min_quantity: next }
    }))
  }

  const addTier = () => {
    setTiers(prev => {
      if (prev.length >= TIER_PALETTE.length) return prev
      const i = prev.length
      const meta = paletteFor(i)
      const maxMin = prev.reduce((m, t) => Math.max(m, t.min_quantity || 1), 0)
      return [...prev, {
        ...meta,
        label: `P${i} · Tier ${i}`,
        price_name: `Tier ${i}`,
        min_quantity: Math.max(maxMin + 1, 2),
        unit_price: '',
      }]
    })
  }

  const removeTier = (idx: number) => {
    setTiers(prev => prev.filter((_, i) => i !== idx))
  }

  // Variant id para ajustes de stock (productos existentes) — la variante elegida en el selector.
  const primaryVariantId = selectedVariantId

  const addStock = async () => {
    if (!primaryVariantId) { setAddStockMsg('Producto sin variante — no se puede ajustar stock'); return }
    const qty = Number(addStockQty)
    if (!(qty > 0)) { setAddStockMsg('Cantidad debe ser > 0'); return }
    const userBranchId = useAuthStore.getState().user?.branch_id
    if (!userBranchId) { setAddStockMsg('Tu usuario no tiene sucursal asignada'); return }
    setAddStockBusy(true)
    setAddStockMsg(null)
    try {
      await inventoryApi.createAdjustment({
        variant_id: primaryVariantId,
        quantity: qty,
        branch_id: userBranchId,
        reason: addStockReason.trim() || 'Reposición POS',
      })
      setAddStockQty('')
      setAddStockReason('')
      setAddStockMsg(`+${qty} agregadas al stock`)
      // El producto del padre no sabe del movimiento: se recarga y se pinta el
      // número nuevo aquí mismo, además de avisarle para que refresque su grid.
      if (product) {
        try {
          const fresh = await productsApi.getById(product.id)
          setRefreshed({
            ...fresh,
            matched_variant_id: product.matched_variant_id ?? fresh.matched_variant_id,
          })
          onSaved?.(fresh)
        } catch {
          // El ajuste sí se aplicó: no se puede fallar aquí. El padre recarga.
          onSaved?.(product)
        }
      }
    } catch (e: any) {
      setAddStockMsg(e?.response?.data?.detail ?? 'Error al ajustar stock')
    } finally {
      setAddStockBusy(false)
    }
  }

  const save = async () => {
    setError(null)
    const p1 = Number(tiers[0]?.unit_price)
    if (!name.trim()) { setError('Nombre requerido'); return }
    if (!(p1 > 0)) { setError('Precio base debe ser > 0'); return }
    if (mode === 'create' && !sku.trim()) { setError('SKU requerido'); return }
    // Marca/Departamento solo obligatorios al crear; en edit los legacy sin marca deben poder guardar.
    if (mode === 'create') {
      if (!brandId) { setError('Marca requerida'); return }
      if (!departmentId) { setError('Departamento requerido'); return }
      // Campos obligatorios adicionales al crear (margen + escaneo + stock real)
      const costNum = Number(cost)
      if (!(costNum > 0)) { setError('Costo requerido (> 0)'); return }
      if (!barcode.trim()) { setError('Código de barras requerido'); return }
      const stockNum = Number(stock)
      if (!(stockNum > 0)) { setError('Stock inicial requerido (> 0)'); return }
    }

    // El primer tier es la fila "Base" — se manda como `price`, no como entrada en prices[].
    const pricesPayload = tiers
      .slice(1)
      .filter(t => Number(t.unit_price) > 0)
      .map(t => ({
        price_name: (t.price_name || '').trim() || 'Tier',
        min_quantity: Math.max(1, Number(t.min_quantity) || 1),
        unit_price: Number(t.unit_price),
      }))

    const cleanPacks = packs
      .map((u) => ({
        name: u.name.trim() || 'Caja',
        barcode: u.barcode.trim() || null,
        units_per_package: parseFloat(u.units_per_package),
        package_price: parseFloat(u.package_price),
      }))
      .filter((u) => !isNaN(u.units_per_package) && u.units_per_package > 0 && !isNaN(u.package_price))

    const costNum = Number(cost)
    const basePayload: any = {
      name: name.trim(),
      sku: sku.trim() || undefined,
      price: p1,
      cost: isFinite(costNum) && costNum >= 0 ? costNum : 0,
      description: desc.trim() || null,
      image_url: imageUrl.trim() || null,
      barcode: barcode.trim() || null,
      prices: pricesPayload,
      packaging_units: cleanPacks,
    }
    // Solo incluir brand/dept si están realmente definidos (string vacío = no tocar).
    if (brandId) basePayload.brand_id = brandId
    if (departmentId) basePayload.department_id = departmentId

    setSaving(true)
    try {
      if (mode === 'create') {
        const payload = {
          ...basePayload,
          sku: sku.trim(),
          initial_stock: Number(stock) || 0,
          uses_inventory: true,
        }
        const saved = await productsApi.create(payload)
        onSaved?.(saved)
        onClose()
      } else if (product) {
        const saved = await productsApi.update(product.id, basePayload)
        onSaved?.(saved)
        setEditing(false)
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al guardar')
    } finally {
      setSaving(false)
    }
  }

  const headerTitle = mode === 'create'
    ? 'Nuevo producto'
    : (editing ? 'Editar producto' : (product?.name ?? ''))

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      onClick={onClose}
    >
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-label={headerTitle || 'Ficha del producto'}
        tabIndex={-1}
        className={`dax-card w-full overflow-hidden max-h-[92vh] flex flex-col outline-none ${editing ? 'max-w-3xl' : 'max-w-md'}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Imagen (solo vista o create sin edición aún) */}
        {!editing && (
          <div
            className="w-full h-40 flex items-center justify-center flex-shrink-0"
            style={{ background: 'var(--dax-elevated)' }}
          >
            {product?.image_url ? (
              <img src={product.image_url} alt="" className="w-full h-full object-cover" />
            ) : (
              <i className="fa-solid fa-box text-5xl" style={{ color: 'var(--dax-text-faint)' }} />
            )}
          </div>
        )}

        <div className="p-5 space-y-4 overflow-y-auto">
          {/* Header con toggle edit */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              {editing ? (
                <>
                  <input
                    className="dax-input w-full text-base font-black"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    placeholder="Nombre del producto"
                  />
                  <div className="grid grid-cols-2 gap-2 mt-2">
                    <input
                      className="dax-input w-full text-xs font-mono"
                      value={sku}
                      onChange={e => setSku(e.target.value)}
                      placeholder={mode === 'create' ? 'SKU *' : 'SKU'}
                    />
                    <input
                      className="dax-input w-full text-xs font-mono"
                      value={barcode}
                      onChange={e => setBarcode(e.target.value)}
                      placeholder={mode === 'create' ? 'Código de barras *' : 'Código de barras'}
                    />
                  </div>
                </>
              ) : (
                <>
                  <h3 className="text-lg font-black leading-tight" style={{ color: 'var(--dax-text)' }}>
                    {headerTitle}
                  </h3>
                  <p className="text-xs font-mono mt-0.5" style={{ color: 'var(--dax-text-faint)' }}>
                    {product?.sku}
                  </p>
                </>
              )}
            </div>
            {mode === 'view' && canEdit && !editing && (
              <button
                onClick={() => setEditing(true)}
                className="flex-shrink-0 flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-lg border-2 transition-colors"
                style={{ borderColor: 'rgba(99,102,241,0.5)', color: '#4f46e5', background: 'rgba(99,102,241,0.08)' }}
                title="Editar producto"
              >
                <i className="fa-solid fa-pen text-[11px]" /> Editar
              </button>
            )}
          </div>

          {/* Stock badge / form */}
          {editing ? (
            mode === 'create' ? (
              <label className="block">
                <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--dax-text-muted)' }}>
                  Stock inicial <span className="text-red-500">*</span>
                </span>
                <input
                  type="number"
                  min="0"
                  step="1"
                  className="dax-input w-full mt-1"
                  value={stock}
                  onChange={e => setStock(e.target.value)}
                />
              </label>
            ) : (
              <div className="rounded-lg p-3" style={{ background: 'var(--dax-elevated)', border: '1px solid var(--dax-border-dim)' }}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--dax-text-muted)' }}>
                    Stock actual
                  </span>
                  <span className={`text-sm font-black tabular-nums px-2 py-0.5 rounded ${
                    displayStock > 0 ? 'bg-emerald-600/20 text-emerald-700' : 'bg-red-600/20 text-red-600'
                  }`}>
                    {displayStock}
                  </span>
                </div>
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
                        <option key={v.id} value={v.id}>{variantDisplayName(v, live?.name ?? v.sku)}</option>
                      ))}
                    </select>
                  </label>
                )}
                <div className="grid grid-cols-[1fr_2fr_auto] gap-2 items-end">
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
                    disabled={addStockBusy || !primaryVariantId || !addStockQty}
                    className="dax-btn-primary text-xs px-3 py-2 disabled:opacity-40 whitespace-nowrap"
                  >
                    {addStockBusy ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-plus" /> Agregar</>}
                  </button>
                </div>
                {addStockMsg && (
                  <p className="text-[10px] mt-2 font-semibold" style={{ color: addStockMsg.startsWith('+') ? '#047857' : '#dc2626' }}>
                    {addStockMsg}
                  </p>
                )}
                {!primaryVariantId && (
                  <p className="text-[9px] mt-1" style={{ color: 'var(--dax-text-faint)' }}>
                    Producto sin variante — guarda el producto primero antes de ajustar stock.
                  </p>
                )}
              </div>
            )
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-end gap-2">
                {/* Sin el nombre, "12 en stock" era el de una talla cualquiera
                    (la escaneada o la primera) y nadie sabía de cuál hablaba. */}
                {variantesVivas.length > 1 && nombreVariante && (
                  <span className="text-[11px] font-bold px-2 py-0.5 rounded-full"
                        style={{ background: 'rgba(99,102,241,0.15)', color: '#4338ca' }}>
                    {nombreVariante}
                  </span>
                )}
                <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                  displayStock > 0 ? 'bg-emerald-600/20 text-emerald-700' : 'bg-red-600/20 text-red-600'
                }`}>
                  {displayStock > 0 ? `${displayStock} en stock` : 'Sin stock'}
                </span>
              </div>

              {/* Existencia y precio de TODAS las tallas: es lo que el cajero
                  necesita para contestar "¿y en M?" sin salir de la ficha. */}
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
                              {variantDisplayName(v, live?.name ?? '')}
                            </td>
                            <td className={`px-2 py-1.5 text-right font-bold tabular-nums ${s > 0 ? '' : 'text-red-600'}`}
                                style={s > 0 ? { color: 'var(--dax-text)' } : undefined}>
                              {s > 0 ? s : 'sin existencia'}
                            </td>
                            <td className="px-2 py-1.5 text-right font-bold tabular-nums" style={{ color: 'var(--dax-text)' }}>
                              {formatCurrency(Number(v.price))}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Tiers — edit (CRUD completo: nombre + min ± + precio ±) o view (lista) */}
          {editing ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--dax-text-muted)' }}>
                  Precios escalonados
                </p>
                <button
                  onClick={addTier}
                  disabled={tiers.length >= TIER_PALETTE.length}
                  className="text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors disabled:opacity-40"
                  style={{ borderColor: 'var(--dax-border)', color: 'var(--dax-text-muted)' }}
                >
                  <i className="fa-solid fa-plus mr-1" /> Agregar precio
                </button>
              </div>
              {tiers.map((t, i) => {
                const priceStep = Number(t.unit_price) >= 100 ? 5 : 1
                return (
                  <div
                    key={i}
                    className="rounded-lg p-2.5 space-y-2"
                    style={{ background: t.bg, border: `1.5px solid ${t.border}` }}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-[9px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded" style={{ color: t.color, background: 'rgba(255,255,255,0.5)' }}>
                        P{i + 1}
                      </span>
                      {i === 0 ? (
                        <span className="text-xs font-bold flex-1" style={{ color: t.color }}>Base</span>
                      ) : (
                        <input
                          type="text"
                          className="flex-1 bg-transparent outline-none text-xs font-bold"
                          style={{ color: t.color }}
                          value={t.price_name}
                          onChange={e => updateTier(i, { price_name: e.target.value })}
                          placeholder="Nombre del tier"
                        />
                      )}
                      {i > 0 && (
                        <button
                          onClick={() => removeTier(i)}
                          className="text-[10px] opacity-60 hover:opacity-100 hover:text-red-600 transition-colors"
                          title="Quitar precio"
                        >
                          <i className="fa-solid fa-xmark" />
                        </button>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      {/* Min quantity stepper */}
                      <div>
                        <p className="text-[9px] font-bold uppercase tracking-wider mb-1" style={{ color: t.color }}>
                          Piezas mín.
                        </p>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => bumpMin(i, -1)}
                            disabled={i === 0 || t.min_quantity <= 1}
                            className="w-9 h-9 rounded-lg font-bold flex items-center justify-center disabled:opacity-30 active:scale-95 transition"
                            style={{ background: 'rgba(255,255,255,0.6)', border: `1px solid ${t.border}`, color: t.color }}
                          >
                            −
                          </button>
                          <input
                            type="number"
                            min="1"
                            step="1"
                            className="flex-1 text-center font-black text-base rounded-lg px-1 py-1.5 outline-none tabular-nums"
                            style={{ background: 'rgba(255,255,255,0.8)', border: `1px solid ${t.border}`, color: t.color }}
                            value={t.min_quantity}
                            onChange={e => updateTier(i, { min_quantity: Math.max(1, parseInt(e.target.value) || 1) })}
                            disabled={i === 0}
                          />
                          <button
                            onClick={() => bumpMin(i, +1)}
                            disabled={i === 0}
                            className="w-9 h-9 rounded-lg font-bold flex items-center justify-center disabled:opacity-30 active:scale-95 transition"
                            style={{ background: 'rgba(255,255,255,0.6)', border: `1px solid ${t.border}`, color: t.color }}
                          >
                            +
                          </button>
                        </div>
                      </div>

                      {/* Unit price stepper */}
                      <div>
                        <p className="text-[9px] font-bold uppercase tracking-wider mb-1" style={{ color: t.color }}>
                          Precio/u
                        </p>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => bumpPrice(i, -priceStep)}
                            className="w-9 h-9 rounded-lg font-bold flex items-center justify-center active:scale-95 transition"
                            style={{ background: 'rgba(255,255,255,0.6)', border: `1px solid ${t.border}`, color: t.color }}
                          >
                            −
                          </button>
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            className="flex-1 text-center font-black text-base rounded-lg px-1 py-1.5 outline-none tabular-nums"
                            style={{ background: 'rgba(255,255,255,0.8)', border: `1px solid ${t.border}`, color: t.color }}
                            value={t.unit_price}
                            onChange={e => updateTier(i, { unit_price: e.target.value })}
                            placeholder="0.00"
                          />
                          <button
                            onClick={() => bumpPrice(i, +priceStep)}
                            className="w-9 h-9 rounded-lg font-bold flex items-center justify-center active:scale-95 transition"
                            style={{ background: 'rgba(255,255,255,0.6)', border: `1px solid ${t.border}`, color: t.color }}
                          >
                            +
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            viewTiers.length > 0 && (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider mb-1.5"
                   style={{ color: 'var(--dax-text-faint)' }}>
                  Precios disponibles
                </p>
                <div
                  className="grid gap-2"
                  style={{ gridTemplateColumns: `repeat(${Math.min(viewTiers.length, 3)}, minmax(0, 1fr))` }}
                >
                  {viewTiers.map((pr, i) => {
                    const meta = paletteFor(i)
                    return (
                      <div key={pr.key}
                           className="rounded-lg p-2 flex flex-col items-center justify-center"
                           style={{ background: meta.bg, border: `1px solid ${meta.border}` }}
                      >
                        <span className="text-[9px] font-bold uppercase tracking-wider" style={{ color: meta.color }}>
                          {pr.name}
                        </span>
                        <span className="text-sm font-black tabular-nums" style={{ color: meta.color }}>
                          {formatCurrency(pr.value)}
                        </span>
                        {pr.min > 1 && (
                          <span className="text-[9px] mt-0.5" style={{ color: 'var(--dax-text-faint)' }}>
                            mín. {pr.min}u
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          )}

          {/* Meta (solo view) */}
          {!editing && product && (
            <div className="grid grid-cols-2 gap-2 text-xs">
              {product.brand_name && <MetaCell label="Marca" value={product.brand_name} />}
              {product.department_name && <MetaCell label="Departamento" value={product.department_name} />}
              {product.min_stock != null && <MetaCell label="Stock mín." value={product.min_stock} />}
              {product.barcode && <MetaCell label="Código de barras" value={product.barcode} />}
              <MetaCell
                label="IVA"
                value={product.has_iva ? `Con IVA ${product.tax_rate ?? 16}%` : 'Sin IVA'}
              />
            </div>
          )}

          {/* Marca + Departamento (solo edit — requeridos por backend) */}
          {editing && (
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--dax-text-muted)' }}>
                  Marca <span className="text-red-500">*</span>
                </span>
                <select className="dax-input w-full mt-1" value={brandId} onChange={e => setBrandId(e.target.value)}>
                  <option value="">— Selecciona —</option>
                  {brands.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--dax-text-muted)' }}>
                  Departamento <span className="text-red-500">*</span>
                </span>
                <select className="dax-input w-full mt-1" value={departmentId} onChange={e => setDepartmentId(e.target.value)}>
                  <option value="">— Selecciona —</option>
                  {departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </label>
            </div>
          )}

          {/* Costo + imagen (solo edit) */}
          {editing && (
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--dax-text-muted)' }}>
                  Costo {mode === 'create' && <span className="text-red-500">*</span>}
                </span>
                <input type="number" min="0" step="0.01" className="dax-input w-full mt-1" value={cost} onChange={e => setCost(e.target.value)} />
              </label>
              <div className="block">
                <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--dax-text-muted)' }}>Foto</span>
                <div className="flex items-center gap-2 mt-1">
                  <div
                    onClick={() => mode !== 'create' && fileRef.current?.click()}
                    className="w-12 h-12 rounded-lg flex-shrink-0 flex items-center justify-center overflow-hidden border-2 border-dashed cursor-pointer"
                    style={{
                      borderColor: 'var(--dax-border)',
                      background: 'var(--dax-elevated)',
                      opacity: mode === 'create' ? 0.5 : 1,
                    }}
                    title={mode === 'create' ? 'Crea el producto primero' : 'Cambiar foto'}
                  >
                    {imgUploading ? (
                      <i className="fa-solid fa-spinner fa-spin text-purple-500" />
                    ) : imageUrl ? (
                      <img src={imageUrl} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <i className="fa-solid fa-camera text-slate-400" />
                    )}
                  </div>
                  <input
                    ref={fileRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      if (f) uploadImage(f)
                      e.target.value = ''
                    }}
                  />
                  <input
                    className="dax-input w-full"
                    value={imageUrl}
                    onChange={e => setImage(e.target.value)}
                    placeholder="o pega URL"
                  />
                  {imageUrl && mode !== 'create' && (
                    <button
                      type="button"
                      onClick={deleteImage}
                      className="text-[10px] text-rose-500 hover:text-rose-600 font-bold flex-shrink-0"
                    >
                      Quitar
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Empaques (cajas) */}
          {editing && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--dax-text-muted)' }}>
                  Empaques (caja, paquete)
                </p>
                <button
                  type="button"
                  onClick={() => setPacks((u) => [...u, { name: 'Caja', barcode: '', units_per_package: '', package_price: '' }])}
                  className="text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors"
                  style={{ borderColor: 'var(--dax-border)', color: 'var(--dax-text-muted)' }}
                >
                  <i className="fa-solid fa-plus mr-1" /> Agregar empaque
                </button>
              </div>
              {packs.length === 0 ? (
                <p className="text-[10px] italic" style={{ color: 'var(--dax-text-faint)' }}>
                  Sin empaques. Agrega uno para vender por caja.
                </p>
              ) : (
                packs.map((u, i) => (
                  <div key={i} className="grid grid-cols-[1fr,1fr,70px,90px,32px] gap-2 items-center">
                    <input
                      className="dax-input text-xs"
                      value={u.name}
                      onChange={(e) => setPacks((arr) => arr.map((x, idx) => idx === i ? { ...x, name: e.target.value } : x))}
                      placeholder="Caja"
                    />
                    <input
                      className="dax-input text-xs"
                      value={u.barcode}
                      onChange={(e) => setPacks((arr) => arr.map((x, idx) => idx === i ? { ...x, barcode: e.target.value } : x))}
                      placeholder="Código (opc.)"
                    />
                    <input
                      className="dax-input text-xs tabular-nums"
                      type="number"
                      step="1"
                      value={u.units_per_package}
                      onChange={(e) => setPacks((arr) => arr.map((x, idx) => idx === i ? { ...x, units_per_package: e.target.value } : x))}
                      placeholder="u/cja"
                    />
                    <input
                      className="dax-input text-xs tabular-nums"
                      type="number"
                      step="0.01"
                      value={u.package_price}
                      onChange={(e) => setPacks((arr) => arr.map((x, idx) => idx === i ? { ...x, package_price: e.target.value } : x))}
                      placeholder="$ caja"
                    />
                    <button
                      type="button"
                      onClick={() => setPacks((arr) => arr.filter((_, idx) => idx !== i))}
                      className="w-8 h-8 rounded-lg flex items-center justify-center text-rose-500 hover:bg-rose-50"
                    >
                      <i className="fa-solid fa-trash text-xs" />
                    </button>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Descripción */}
          {editing ? (
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--dax-text-muted)' }}>Descripción</span>
              <textarea className="dax-input w-full mt-1" rows={3} value={desc} onChange={e => setDesc(e.target.value)} />
            </label>
          ) : (
            product?.description && (
              <p className="text-sm leading-relaxed" style={{ color: 'var(--dax-text-muted)' }}>
                {product.description}
              </p>
            )
          )}

          {error && <p className="text-xs text-red-500 font-semibold">{error}</p>}

          {/* Botones */}
          <div className="flex flex-wrap gap-2 pt-1">
            {editing ? (
              <>
                <button onClick={cancelEdit} className="flex-1 dax-btn-secondary text-sm justify-center" disabled={saving}>
                  Cancelar
                </button>
                <button onClick={save} className="flex-1 dax-btn-primary text-sm justify-center" disabled={saving}>
                  {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> {mode === 'create' ? 'Crear producto' : 'Guardar cambios'}</>}
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={onClose}
                  className="flex-1 dax-btn-secondary text-sm justify-center"
                >
                  Cerrar
                </button>
                {onAddToCart && product && displayStock > 0 && (
                  <button
                    onClick={() => { onAddToCart(product); onClose() }}
                    className="flex-1 dax-btn-primary text-sm justify-center"
                  >
                    <i className="fa-solid fa-cart-plus" /> Agregar
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
