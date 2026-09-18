import { Fragment, useEffect, useState, useCallback, useRef, type FormEvent } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { productsApi, type BranchStatusPatch } from '../../api/products'
import { useAuthStore } from '../../store/authStore'
import { useIsBranchUser } from '../../components/branch/useIsBranchUser'
import { ProductsBranchView } from '../../components/branch/ProductsBranchView'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import type { Product, Department, Brand, ProductBranchStatus } from '../../types/products'
import { formatCurrency } from '../../utils/currency'
import { sortByName } from '../../utils/sortByName'
import { toast } from '../../store/toastStore'
import { ProductImageUploader } from '../../components/products/ProductImageUploader'
import { expandVariantRows, grupoDeVariantes, nombreDeVariante, priceRange, sumStock } from './variantRows'

const SINGULAR_GRUPO = { tallas: 'talla', colores: 'color', variantes: 'variante' } as const

const HQ_ROLES = ['ADMINISTRADOR', 'DUEÑO']
const CAN_EDIT_ROLES = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO']
const BRANCH_EDIT_ROLES = ['GERENTE', 'CAJERO']

// ─── Import Modal ──────────────────────────────────────────────────────────────

function ImportModal({ onClose, onDone, isHQ }: { onClose: () => void; onDone: () => void; isHQ: boolean }) {
  const [file, setFile] = useState<File | null>(null)
  const [scope, setScope] = useState<'branch' | 'all' | 'selected'>('branch')
  const [result, setResult] = useState<{ created: number; updated: number; failed: number; errors: string[] } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleUpload = async () => {
    if (!file) return
    setLoading(true); setError(null)
    try {
      const uploadScope = isHQ ? scope : 'branch'
      const res = await productsApi.uploadProducts(file, uploadScope)
      setResult(res)
      if (res.created > 0 || res.updated > 0) onDone()
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al importar. Revisa el archivo.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="dax-card p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-black text-white">Importar productos</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
        </div>

        {!result ? (
          <div className="space-y-4">
            <p className="text-slate-400 text-xs leading-relaxed">
              Sube un archivo Excel (.xlsx) o CSV con tus productos. Los productos nuevos se activarán automáticamente en tu sucursal.
            </p>

            {isHQ && (
              <div>
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                  Alcance de importación
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setScope('all')}
                    className={`py-2 rounded-xl text-xs font-semibold border transition-colors ${
                      scope === 'all'
                        ? 'border-indigo-500 bg-indigo-600/20 text-white'
                        : 'border-slate-700/50 text-slate-400 hover:border-slate-600 hover:text-white'
                    }`}
                  >
                    <i className="fa-solid fa-globe mr-1.5" />
                    Todas las sucursales
                  </button>
                  <button
                    type="button"
                    onClick={() => setScope('branch')}
                    className={`py-2 rounded-xl text-xs font-semibold border transition-colors ${
                      scope === 'branch'
                        ? 'border-indigo-500 bg-indigo-600/20 text-white'
                        : 'border-slate-700/50 text-slate-400 hover:border-slate-600 hover:text-white'
                    }`}
                  >
                    <i className="fa-solid fa-building mr-1.5" />
                    Solo HQ
                  </button>
                </div>
              </div>
            )}

            <button
              onClick={async () => {
                try {
                  await productsApi.downloadTemplate()
                } catch {
                  toast.error('No se pudo descargar la plantilla. Reintenta en unos segundos.')
                }
              }}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-semibold border border-slate-700 text-slate-400 hover:text-white hover:border-slate-500 transition-colors"
            >
              <i className="fa-solid fa-file-excel text-emerald-400" /> Descargar plantilla con productos actuales
            </button>

            <div
              onClick={() => fileRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${file ? 'border-indigo-500/50 bg-indigo-600/5' : 'border-slate-700 hover:border-slate-500'}`}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".xlsx,.xlsm,.xls,.csv"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              {file ? (
                <>
                  <i className="fa-solid fa-file-check text-indigo-400 text-2xl mb-2 block" />
                  <p className="text-white text-sm font-semibold">{file.name}</p>
                  <p className="text-slate-500 text-xs mt-0.5">{(file.size / 1024).toFixed(1)} KB</p>
                </>
              ) : (
                <>
                  <i className="fa-solid fa-cloud-arrow-up text-slate-500 text-2xl mb-2 block" />
                  <p className="text-slate-400 text-sm">Clic para seleccionar archivo</p>
                  <p className="text-slate-600 text-xs mt-0.5">.xlsx, .xls, .csv</p>
                </>
              )}
            </div>

            {error && <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>}

            <div className="flex gap-2">
              <button onClick={onClose} className="dax-btn-secondary flex-1">Cancelar</button>
              <button
                onClick={handleUpload}
                disabled={!file || loading}
                className="dax-btn-primary flex-1 justify-center disabled:opacity-40"
              >
                {loading ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-file-import" /> Importar</>}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-3">
                <p className="text-2xl font-black text-emerald-400">{result.created}</p>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mt-0.5">Nuevos</p>
              </div>
              <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-xl p-3">
                <p className="text-2xl font-black text-indigo-400">{result.updated}</p>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mt-0.5">Actualizados</p>
              </div>
              <div className={`${result.failed > 0 ? 'bg-red-500/10 border-red-500/20' : 'bg-slate-800 border-slate-700/50'} border rounded-xl p-3`}>
                <p className={`text-2xl font-black ${result.failed > 0 ? 'text-red-400' : 'text-slate-500'}`}>{result.failed}</p>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mt-0.5">Fallidos</p>
              </div>
            </div>

            {result.errors.length > 0 && (
              <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-3 max-h-32 overflow-y-auto">
                <p className="text-[10px] font-bold text-red-400 uppercase tracking-wider mb-1.5">Errores</p>
                {result.errors.map((e, i) => (
                  <p key={i} className="text-red-300 text-xs">{e}</p>
                ))}
              </div>
            )}

            <button onClick={onClose} className="w-full dax-btn-primary justify-center">
              <i className="fa-solid fa-check" /> Cerrar
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Branch Status Editor (CAJERO/GERENTE) ─────────────────────────────────────

/**
 * Variantes sobre las que hay que escribir el PBS del producto.
 *
 * Antes esto devolvía solo `variants[0]`: apagar el POS o fijar un precio de
 * sucursal dejaba las demás tallas vendiéndose, y al precio viejo. Es un bug
 * de dinero, así que el cambio va a TODAS las tallas vivas (el backend ya
 * excluye las retiradas de `variants`).
 *
 * Aquí no se usa `/branch-status/bulk-toggle` a propósito: ese endpoint es
 * admin-only y esta ficha la usan CAJERO/GERENTE, que sí pueden hacer el
 * PATCH de su propia sucursal.
 */
function pickVariantIds(p: Product): string[] {
  const vivas = (p.variants ?? []).map((v) => v.id)
  if (vivas.length > 0) return vivas
  const primero = p.branch_statuses?.[0]?.variant_id
  return primero ? [primero] : []
}

/**
 * Toma el PBS existente para la sucursal del usuario (si existe).
 * Si no hay, devuelve valores por defecto sensatos para iniciar la edición.
 */
function pickBranchStatus(p: Product, branchId: number | null): ProductBranchStatus | null {
  if (!branchId) return null
  return p.branch_statuses?.find(s => s.branch_id === branchId) ?? null
}

interface BranchStatusEditorProps {
  product: Product
  branchId: number
  onSaved: (updated: ProductBranchStatus) => void
  onCancel: () => void
}

function BranchStatusEditor({ product, branchId, onSaved, onCancel }: BranchStatusEditorProps) {
  const existing = pickBranchStatus(product, branchId)
  const variantIds = pickVariantIds(product)
  const grupo = grupoDeVariantes(product.variants ?? [])

  const [priceOverride, setPriceOverride] = useState<string>(
    existing?.price_override != null ? String(existing.price_override) : ''
  )
  const [minStock, setMinStock] = useState<string>(
    existing?.min_stock_alert != null ? String(existing.min_stock_alert) : ''
  )
  const [maxStock, setMaxStock] = useState<string>(
    existing?.max_stock_limit != null ? String(existing.max_stock_limit) : ''
  )
  const [isActivePos, setIsActivePos] = useState<boolean>(existing?.is_active_pos ?? true)
  const [isActiveHq, setIsActiveHq] = useState<boolean>(existing?.is_active_hq ?? true)
  const [isVisible, setIsVisible] = useState<boolean>(existing?.is_visible ?? true)

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Sólo enviamos los campos que realmente cambiaron vs el estado inicial
  // del PBS. Para un PBS nuevo (existing=null), enviamos todo lo que el
  // usuario haya tocado para que el backend lo cree con esos valores.
  const buildPatch = (): BranchStatusPatch => {
    const patch: BranchStatusPatch = {}

    // price_override: string vacío → null (limpiar override)
    const initialPrice = existing?.price_override ?? null
    const currentPrice = priceOverride.trim() === '' ? null : Number(priceOverride)
    if (currentPrice !== initialPrice) patch.price_override = currentPrice

    const initialMin = existing?.min_stock_alert ?? null
    const currentMin = minStock.trim() === '' ? null : Number(minStock)
    if (currentMin !== initialMin) patch.min_stock_alert = currentMin

    const initialMax = existing?.max_stock_limit ?? null
    const currentMax = maxStock.trim() === '' ? null : Number(maxStock)
    if (currentMax !== initialMax) patch.max_stock_limit = currentMax

    if ((existing?.is_active_pos ?? true) !== isActivePos) patch.is_active_pos = isActivePos
    if ((existing?.is_active_hq ?? true) !== isActiveHq) patch.is_active_hq = isActiveHq
    if ((existing?.is_visible ?? true) !== isVisible) patch.is_visible = isVisible

    return patch
  }

  const handleSave = async () => {
    if (variantIds.length === 0) { setError('No se encontró una variante editable para este producto.'); return }

    const patch = buildPatch()
    if (Object.keys(patch).length === 0) {
      toast.info('No hay cambios que guardar.')
      onCancel()
      return
    }

    // Validación numérica mínima — evitar enviar NaN
    if (patch.price_override !== undefined && patch.price_override !== null && !Number.isFinite(patch.price_override)) {
      setError('Precio inválido.'); return
    }
    if (patch.min_stock_alert !== undefined && patch.min_stock_alert !== null && !Number.isFinite(patch.min_stock_alert)) {
      setError('Stock mínimo inválido.'); return
    }
    if (patch.max_stock_limit !== undefined && patch.max_stock_limit !== null && !Number.isFinite(patch.max_stock_limit)) {
      setError('Stock máximo inválido.'); return
    }

    setSaving(true); setError(null)
    try {
      // Una escritura por talla: el endpoint es por variante y no hay bulk
      // disponible para este rol. La primera (la principal) es la que la
      // tabla muestra, así que es la que devolvemos.
      let principal: ProductBranchStatus | null = null
      for (const vid of variantIds) {
        const res = await productsApi.updateBranchStatus(vid, patch)
        if (principal === null) principal = res
      }
      toast.success(
        variantIds.length > 1
          ? `Cambios guardados en tu sucursal para las ${variantIds.length} ${grupo}.`
          : 'Cambios guardados en tu sucursal.',
      )
      onSaved(principal as ProductBranchStatus)
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (e?.response?.status === 403) {
        setError('No tienes permiso para editar esta sucursal.')
      } else if (e?.response?.status === 404) {
        setError('Producto no disponible en tu sucursal.')
      } else {
        setError(typeof detail === 'string' ? detail : 'Error al guardar los cambios.')
      }
    } finally {
      setSaving(false)
    }
  }

  const clearOverride = () => setPriceOverride('')

  return (
    <div className="bg-slate-800/60 border border-indigo-500/20 rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-indigo-300">
            <i className="fa-solid fa-store mr-1.5" />
            Configuración por sucursal
          </p>
          <p className="text-slate-400 text-xs mt-0.5">
            Los cambios aquí afectan únicamente a <span className="text-white font-semibold">tu sucursal</span>.
            El precio base del producto no se modifica.
          </p>
          {variantIds.length > 1 && (
            <p className="text-slate-400 text-xs mt-0.5">
              Se aplican a las <span className="text-white font-semibold">{variantIds.length} {grupo}</span> del producto.
            </p>
          )}
        </div>
        <span className="text-[10px] text-slate-500 font-mono">
          Base: {formatCurrency(product.price ?? 0)}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* Precio override */}
        <div className="sm:col-span-1">
          <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
            Precio de venta en sucursal
          </label>
          <div className="flex items-center gap-1.5">
            <input
              type="number" min="0" step="0.01"
              className="dax-input w-full text-xs"
              placeholder={`Hereda ${formatCurrency(product.price ?? 0)}`}
              value={priceOverride}
              onChange={e => setPriceOverride(e.target.value)}
            />
            <button
              type="button"
              onClick={clearOverride}
              disabled={priceOverride === ''}
              className="px-2 py-1.5 rounded-lg border border-slate-700/50 text-[10px] font-semibold text-slate-400 hover:text-white hover:border-slate-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
              title="Vaciar override (volver a usar el precio base)"
            >
              Limpiar
            </button>
          </div>
          <p className="text-[10px] text-slate-600 mt-1">Vacío = usa el precio base del producto.</p>
        </div>

        {/* Stock min */}
        <div>
          <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
            Stock mínimo (alerta)
          </label>
          <input
            type="number" min="0" step="1"
            className="dax-input w-full text-xs"
            placeholder="opcional"
            value={minStock}
            onChange={e => setMinStock(e.target.value)}
          />
        </div>

        {/* Stock max */}
        <div>
          <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
            Stock máximo
          </label>
          <input
            type="number" min="0" step="1"
            className="dax-input w-full text-xs"
            placeholder="opcional"
            value={maxStock}
            onChange={e => setMaxStock(e.target.value)}
          />
        </div>
      </div>

      {/* Flags */}
      <div className="flex flex-wrap gap-4 pt-1">
        <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={isActivePos}
            onChange={e => setIsActivePos(e.target.checked)}
            className="rounded"
          />
          Activo en POS
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={isActiveHq}
            onChange={e => setIsActiveHq(e.target.checked)}
            className="rounded"
          />
          Activo en HQ
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={isVisible}
            onChange={e => setIsVisible(e.target.checked)}
            className="rounded"
          />
          Visible
        </label>
      </div>

      {error && (
        <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          <i className="fa-solid fa-circle-exclamation mr-1.5" />{error}
        </p>
      )}

      <div className="flex items-center justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="dax-btn-secondary text-xs"
        >
          Cancelar
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving || variantIds.length === 0}
          className="dax-btn text-xs flex items-center gap-1.5 disabled:opacity-50"
        >
          {saving ? <i className="fa-solid fa-spinner fa-spin text-[10px]" /> : <i className="fa-solid fa-floppy-disk text-[10px]" />}
          Guardar
        </button>
      </div>
    </div>
  )
}

// ─── Create Product Mini Modal (CAJERO/GERENTE) ────────────────────────────────

interface CreateProductMiniModalProps {
  brands: Brand[]
  departments: Department[]
  onClose: () => void
  onCreated: (product: Product) => void
}

function CreateProductMiniModal({ brands, departments, onClose, onCreated }: CreateProductMiniModalProps) {
  const [name, setName] = useState('')
  const [sku, setSku] = useState('')
  const [price, setPrice] = useState('')
  const [cost, setCost] = useState('')
  const [departmentId, setDepartmentId] = useState('')
  const [brandId, setBrandId] = useState('')
  const [barcode, setBarcode] = useState('')

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) { setError('El nombre es requerido.'); return }
    if (!sku.trim()) { setError('El SKU es requerido.'); return }
    const priceNum = Number(price)
    const costNum = Number(cost)
    if (!Number.isFinite(priceNum) || priceNum < 0) { setError('Precio inválido.'); return }
    if (!Number.isFinite(costNum) || costNum < 0) { setError('Costo inválido.'); return }
    if (!departmentId) { setError('Selecciona un departamento.'); return }
    if (!brandId) { setError('Selecciona una marca.'); return }

    setSaving(true); setError(null)
    try {
      // El backend crea automáticamente el PBS para la sucursal del CAJERO;
      // no es necesario enviar branch_id.
      const created = await productsApi.create({
        name: name.trim(),
        sku: sku.trim(),
        price: priceNum,
        cost: costNum,
        department_id: departmentId,
        brand_id: brandId,
        barcode: barcode.trim() || null,
      })
      toast.success('Producto creado. Disponible en tu sucursal.')
      onCreated(created)
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (e?.response?.status === 409) {
        setError(`SKU '${sku.trim()}' ya existe en la organización.`)
      } else if (e?.response?.status === 422) {
        setError(typeof detail === 'string' ? detail : 'Faltan campos requeridos.')
      } else {
        setError(typeof detail === 'string' ? detail : 'Error al crear el producto.')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <form
        onSubmit={handleSubmit}
        className="dax-card p-5 w-full max-w-md space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-black text-white">Nuevo producto</h3>
            <p className="text-slate-500 text-[11px] mt-0.5">
              Se creará activo en <span className="text-indigo-400 font-semibold">tu sucursal</span>.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-500 hover:text-white"
            aria-label="Cerrar"
          >
            <i className="fa-solid fa-xmark text-lg" />
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3">
          <div>
            <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Nombre *
            </label>
            <input
              className="dax-input w-full text-sm"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="ej. Martillo de bola 16oz"
              autoFocus
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                SKU *
              </label>
              <input
                className="dax-input w-full text-sm font-mono"
                value={sku}
                onChange={e => setSku(e.target.value)}
                placeholder="SKU-001"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                Código de barras
              </label>
              <input
                className="dax-input w-full text-sm font-mono"
                value={barcode}
                onChange={e => setBarcode(e.target.value)}
                placeholder="opcional"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                Precio *
              </label>
              <input
                type="number" min="0" step="0.01"
                className="dax-input w-full text-sm"
                value={price}
                onChange={e => setPrice(e.target.value)}
                placeholder="0.00"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                Costo *
              </label>
              <input
                type="number" min="0" step="0.01"
                className="dax-input w-full text-sm"
                value={cost}
                onChange={e => setCost(e.target.value)}
                placeholder="0.00"
              />
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Departamento *
            </label>
            <select
              className="dax-input w-full text-sm"
              value={departmentId}
              onChange={e => setDepartmentId(e.target.value)}
            >
              <option value="">Selecciona...</option>
              {departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Marca *
            </label>
            <select
              className="dax-input w-full text-sm"
              value={brandId}
              onChange={e => setBrandId(e.target.value)}
            >
              <option value="">Selecciona...</option>
              {brands.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
        </div>

        {error && (
          <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
            <i className="fa-solid fa-circle-exclamation mr-1.5" />{error}
          </p>
        )}

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="dax-btn-secondary text-sm"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={saving}
            className="dax-btn text-sm flex items-center gap-1.5 disabled:opacity-50"
          >
            {saving ? <i className="fa-solid fa-spinner fa-spin text-xs" /> : <i className="fa-solid fa-plus text-xs" />}
            Crear
          </button>
        </div>
      </form>
    </div>
  )
}

// ─── Product Modal ─────────────────────────────────────────────────────────────

interface PriceRow {
  id?: string
  price_name: string
  min_quantity: number
  unit_price: number
}

interface PackagingRow {
  id?: string
  name: string
  barcode: string
  units_per_package: number
  package_price: number
}

interface ProductModalProps {
  product: Product | null  // null = create mode
  onClose: () => void
  onSaved: () => void
  brands: Brand[]
  departments: Department[]
  isCajero?: boolean
}

function ProductModal({ product, onClose, onSaved, brands, departments, isCajero = false }: ProductModalProps) {
  const isEdit = !!product

  // editedProduct tracks server-reflected state (e.g. after image upload).
  const [editedProduct, setEditedProduct] = useState<Product | null>(product ?? null)

  const [name, setName] = useState(product?.name ?? '')
  const [sku, setSku] = useState(product?.sku ?? '')
  const [barcode, setBarcode] = useState(product?.barcode ?? '')
  const [unit, setUnit] = useState(product?.unit ?? 'pza')
  const [price, setPrice] = useState(String(product?.price ?? ''))
  const [cost, setCost] = useState(String(product?.cost ?? ''))
  const [description, setDescription] = useState(product?.description ?? '')
  const [imageUrl, setImageUrl] = useState(product?.image_url ?? '')
  const [hasIva, setHasIva] = useState(product?.has_iva ?? false)
  const [taxRate, setTaxRate] = useState(String(product?.tax_rate ?? 16))
  const [usesInventory, setUsesInventory] = useState(product?.uses_inventory ?? true)
  const [brandId, setBrandId] = useState(product?.brand_id ?? '')
  const [deptId, setDeptId] = useState(product?.department?.id ?? '')

  const [prices, setPrices] = useState<PriceRow[]>(
    product?.prices?.map(p => ({
      id: p.id,
      price_name: p.price_name,
      min_quantity: p.min_quantity,
      unit_price: p.unit_price,
    })) ?? []
  )

  const [packagings, setPackagings] = useState<PackagingRow[]>(
    product?.packaging_units?.map(u => ({
      id: u.id,
      name: u.name,
      barcode: u.barcode ?? '',
      units_per_package: u.units_per_package,
      package_price: u.package_price,
    })) ?? []
  )

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const addPrice = () =>
    setPrices(prev => [...prev, { price_name: '', min_quantity: 0, unit_price: 0 }])

  const removePrice = (i: number) =>
    setPrices(prev => prev.filter((_, idx) => idx !== i))

  const updatePrice = (i: number, field: keyof PriceRow, val: string | number) =>
    setPrices(prev => prev.map((p, idx) => idx === i ? { ...p, [field]: val } : p))

  const addPackaging = () =>
    setPackagings(prev => [...prev, { name: 'Caja', barcode: '', units_per_package: 1, package_price: 0 }])

  const removePackaging = (i: number) =>
    setPackagings(prev => prev.filter((_, idx) => idx !== i))

  const updatePackaging = (i: number, field: keyof PackagingRow, val: string | number) =>
    setPackagings(prev => prev.map((u, idx) => idx === i ? { ...u, [field]: val } : u))

  const handleSave = async () => {
    if (!name.trim() || !sku.trim()) { setError('Nombre y SKU son requeridos'); return }
    setSaving(true)
    setError(null)
    try {
      const payload = {
        name: name.trim(),
        sku: sku.trim(),
        barcode: barcode.trim() || null,
        unit: unit.trim() || 'pza',
        price: Number(price),
        cost: Number(cost),
        description: description.trim() || null,
        image_url: imageUrl.trim() || null,
        has_iva: hasIva,
        tax_rate: hasIva ? Number(taxRate) : 0,
        uses_inventory: usesInventory,
        brand_id: brandId || null,
        department_id: deptId || null,
        prices: prices.map(p => ({
          price_name: p.price_name,
          min_quantity: Number(p.min_quantity),
          unit_price: Number(p.unit_price),
        })),
        packaging_units: packagings.map(u => ({
          name: u.name,
          barcode: u.barcode || null,
          units_per_package: Number(u.units_per_package),
          package_price: Number(u.package_price),
        })),
      }
      if (isEdit) {
        await productsApi.update(product!.id, payload)
      } else {
        await productsApi.create({ ...payload, initial_stock: 0 } as any)
      }
      onSaved()
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error al guardar')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl"
        style={{ background: 'var(--dax-surface)', border: '1px solid var(--dax-border)' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: 'var(--dax-border-dim)' }}>
          <h2 className="font-bold text-base" style={{ color: 'var(--dax-text)' }}>
            {isEdit ? 'Editar Producto' : 'Nuevo Producto'}
          </h2>
          <button onClick={onClose} className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 transition-colors">
            <i className="fa-solid fa-xmark text-xs" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-5">
          {/* Banner informativo para CAJERO en modo edición */}
          {isCajero && isEdit && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-xl bg-amber-500/10 border border-amber-500/20">
              <i className="fa-solid fa-circle-info text-amber-400 text-xs mt-0.5 flex-shrink-0" />
              <p className="text-amber-300 text-xs leading-relaxed">
                Puedes editar el nombre, descripción e imagen. El precio, costo, SKU y código de barras son de solo lectura para tu rol.
              </p>
            </div>
          )}
          {/* Datos básicos */}
          <section className="space-y-3">
            <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--dax-text-faint)' }}>Datos generales</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-xs mb-1" style={{ color: 'var(--dax-text-muted)' }}>Nombre *</label>
                <input className="dax-input w-full" value={name} onChange={e => setName(e.target.value)} placeholder="Nombre del producto" />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--dax-text-muted)' }}>SKU *</label>
                <input className={`dax-input w-full font-mono ${isCajero ? 'opacity-50 cursor-not-allowed' : ''}`} value={sku} onChange={e => !isCajero && setSku(e.target.value)} placeholder="SKU-001" readOnly={isCajero} title={isCajero ? 'CAJERO no puede modificar el SKU' : undefined} />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--dax-text-muted)' }}>Código de barras</label>
                <input className={`dax-input w-full font-mono ${isCajero ? 'opacity-50 cursor-not-allowed' : ''}`} value={barcode} onChange={e => !isCajero && setBarcode(e.target.value)} placeholder="7501055..." readOnly={isCajero} title={isCajero ? 'CAJERO no puede modificar el código de barras' : undefined} />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--dax-text-muted)' }}>Precio base *</label>
                <input className={`dax-input w-full ${isCajero ? 'opacity-50 cursor-not-allowed' : ''}`} type="number" min="0" step="0.01" value={price} onChange={e => !isCajero && setPrice(e.target.value)} readOnly={isCajero} title={isCajero ? 'CAJERO no puede modificar el precio base' : undefined} />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--dax-text-muted)' }}>Costo</label>
                <input className={`dax-input w-full ${isCajero ? 'opacity-50 cursor-not-allowed' : ''}`} type="number" min="0" step="0.01" value={cost} onChange={e => !isCajero && setCost(e.target.value)} readOnly={isCajero} title={isCajero ? 'CAJERO no puede modificar el costo' : undefined} />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--dax-text-muted)' }}>Unidad de venta</label>
                <select className="dax-input w-full" value={unit} onChange={e => setUnit(e.target.value)}>
                  <option value="pza">Pieza (pza)</option>
                  <option value="kg">Kilogramo (kg)</option>
                  <option value="lt">Litro (lt)</option>
                  <option value="cja">Caja (cja)</option>
                  <option value="par">Par</option>
                  <option value="mt">Metro (mt)</option>
                  <option value="srv">Servicio</option>
                </select>
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--dax-text-muted)' }}>Marca</label>
                <select className="dax-input w-full" value={brandId} onChange={e => setBrandId(e.target.value)}>
                  <option value="">Sin marca</option>
                  {brands.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--dax-text-muted)' }}>Departamento</label>
                <select className="dax-input w-full" value={deptId} onChange={e => setDeptId(e.target.value)}>
                  <option value="">Sin departamento</option>
                  {departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </div>
              {isEdit && editedProduct ? (
                <ProductImageUploader
                  product={editedProduct}
                  onUpdated={(updated) => {
                    setEditedProduct(updated)
                    setImageUrl(updated.image_url ?? '')
                  }}
                />
              ) : (
                <div className="col-span-2">
                  <label className="block text-xs mb-1" style={{ color: 'var(--dax-text-muted)' }}>URL de imagen</label>
                  <input className="dax-input w-full" value={imageUrl} onChange={e => setImageUrl(e.target.value)} placeholder="https://..." />
                </div>
              )}
              <div className="col-span-2">
                <label className="block text-xs mb-1" style={{ color: 'var(--dax-text-muted)' }}>Descripción</label>
                <textarea className="dax-input w-full" rows={2} value={description} onChange={e => setDescription(e.target.value)} placeholder="Descripción opcional" />
              </div>
              <div className="col-span-2 flex flex-wrap items-center gap-4">
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="has_iva" checked={hasIva} onChange={e => setHasIva(e.target.checked)} className="rounded" />
                  <label htmlFor="has_iva" className="text-xs cursor-pointer" style={{ color: 'var(--dax-text-muted)' }}>
                    Aplica IVA
                  </label>
                  {hasIva && (
                    <div className="flex items-center gap-1">
                      <input
                        className="dax-input w-16 text-xs text-center"
                        type="number" min="0" max="100" step="0.5"
                        value={taxRate}
                        onChange={e => setTaxRate(e.target.value)}
                      />
                      <span className="text-xs" style={{ color: 'var(--dax-text-faint)' }}>%</span>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="uses_inventory" checked={usesInventory} onChange={e => setUsesInventory(e.target.checked)} className="rounded" />
                  <label htmlFor="uses_inventory" className="text-xs cursor-pointer" style={{ color: 'var(--dax-text-muted)' }}>
                    Controla inventario
                  </label>
                </div>
              </div>
            </div>
          </section>

          {/* Precios escalonados */}
          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--dax-text-faint)' }}>
                Precios escalonados
              </p>
              <button
                onClick={addPrice}
                className="flex items-center gap-1 text-[10px] font-bold text-indigo-400 hover:text-indigo-300 px-2 py-0.5 rounded hover:bg-indigo-500/10 transition-colors"
              >
                <i className="fa-solid fa-plus" /> Agregar tier
              </button>
            </div>
            {prices.length === 0 ? (
              <p className="text-xs py-2 text-center" style={{ color: 'var(--dax-text-faint)' }}>Sin precios adicionales (solo precio base)</p>
            ) : (
              <div className="space-y-2">
                {prices.map((p, i) => (
                  <div key={i} className="grid grid-cols-[1fr_80px_90px_28px] gap-2 items-end">
                    <div>
                      {i === 0 && <label className="block text-[10px] mb-0.5" style={{ color: 'var(--dax-text-faint)' }}>Nombre</label>}
                      <input
                        className="dax-input w-full text-xs"
                        value={p.price_name}
                        onChange={e => updatePrice(i, 'price_name', e.target.value)}
                        placeholder="ej. Mayoreo"
                      />
                    </div>
                    <div>
                      {i === 0 && <label className="block text-[10px] mb-0.5" style={{ color: 'var(--dax-text-faint)' }}>Min. piezas</label>}
                      <input
                        className="dax-input w-full text-xs"
                        type="number" min="1"
                        value={p.min_quantity}
                        onChange={e => updatePrice(i, 'min_quantity', Number(e.target.value))}
                      />
                    </div>
                    <div>
                      {i === 0 && <label className="block text-[10px] mb-0.5" style={{ color: 'var(--dax-text-faint)' }}>Precio/u</label>}
                      <input
                        className="dax-input w-full text-xs"
                        type="number" min="0" step="0.01"
                        value={p.unit_price}
                        onChange={e => updatePrice(i, 'unit_price', Number(e.target.value))}
                      />
                    </div>
                    <button
                      onClick={() => removePrice(i)}
                      className="h-8 w-7 flex items-center justify-center text-slate-500 hover:text-red-400 transition-colors rounded"
                    >
                      <i className="fa-solid fa-xmark text-xs" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Empaques */}
          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--dax-text-faint)' }}>
                Empaques / Cajas
              </p>
              <button
                onClick={addPackaging}
                className="flex items-center gap-1 text-[10px] font-bold text-indigo-400 hover:text-indigo-300 px-2 py-0.5 rounded hover:bg-indigo-500/10 transition-colors"
              >
                <i className="fa-solid fa-plus" /> Agregar empaque
              </button>
            </div>
            {packagings.length === 0 ? (
              <p className="text-xs py-2 text-center" style={{ color: 'var(--dax-text-faint)' }}>Sin empaques definidos</p>
            ) : (
              <div className="space-y-2">
                {packagings.map((u, i) => (
                  <div key={i} className="grid grid-cols-[1fr_70px_90px_1fr_28px] gap-2 items-end">
                    <div>
                      {i === 0 && <label className="block text-[10px] mb-0.5" style={{ color: 'var(--dax-text-faint)' }}>Nombre</label>}
                      <input
                        className="dax-input w-full text-xs"
                        value={u.name}
                        onChange={e => updatePackaging(i, 'name', e.target.value)}
                        placeholder="Caja"
                      />
                    </div>
                    <div>
                      {i === 0 && <label className="block text-[10px] mb-0.5" style={{ color: 'var(--dax-text-faint)' }}>Unidades</label>}
                      <input
                        className="dax-input w-full text-xs"
                        type="number" min="1"
                        value={u.units_per_package}
                        onChange={e => updatePackaging(i, 'units_per_package', Number(e.target.value))}
                      />
                    </div>
                    <div>
                      {i === 0 && <label className="block text-[10px] mb-0.5" style={{ color: 'var(--dax-text-faint)' }}>Precio/caja</label>}
                      <input
                        className="dax-input w-full text-xs"
                        type="number" min="0" step="0.01"
                        value={u.package_price}
                        onChange={e => updatePackaging(i, 'package_price', Number(e.target.value))}
                      />
                    </div>
                    <div>
                      {i === 0 && <label className="block text-[10px] mb-0.5" style={{ color: 'var(--dax-text-faint)' }}>Código de barras</label>}
                      <input
                        className="dax-input w-full text-xs font-mono"
                        value={u.barcode}
                        onChange={e => updatePackaging(i, 'barcode', e.target.value)}
                        placeholder="Opcional"
                      />
                    </div>
                    <button
                      onClick={() => removePackaging(i)}
                      className="h-8 w-7 flex items-center justify-center text-slate-500 hover:text-red-400 transition-colors rounded"
                    >
                      <i className="fa-solid fa-xmark text-xs" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>

          {error && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              <i className="fa-solid fa-circle-exclamation mr-1.5" />{error}
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t" style={{ borderColor: 'var(--dax-border-dim)' }}>
          <button onClick={onClose} className="dax-btn-secondary text-sm" disabled={saving}>
            Cancelar
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="dax-btn text-sm flex items-center gap-2"
          >
            {saving ? <i className="fa-solid fa-spinner fa-spin text-xs" /> : <i className="fa-solid fa-floppy-disk text-xs" />}
            {isEdit ? 'Guardar cambios' : 'Crear producto'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main Products Page ─────────────────────────────────────────────────────────

export function Products() {
  // Roles de sucursal (CAJERO/GERENTE) ven la vista simplificada con modales
  // y acciones por fila; HQ conserva la matriz multi-sucursal completa.
  if (useIsBranchUser()) return <ProductsBranchView />
  return <ProductsHQView />
}

// Separado para no romper Rules of Hooks: el return condicional de arriba
// no puede convivir con hooks en el mismo componente.
function ProductsHQView() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user } = useAuthStore()
  const isHQ = HQ_ROLES.includes(user?.role ?? '')
  const canEdit = CAN_EDIT_ROLES.includes(user?.role ?? '')
  // CAJERO/GERENTE tienen además el editor PBS inline para toggles rápidos.
  const isBranchEditor = BRANCH_EDIT_ROLES.includes(user?.role ?? '') && user?.branch_id != null

  const [products, setProducts] = useState<Product[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [brands, setBrands] = useState<Brand[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [deptId, setDeptId] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Modal state
  const [modalProduct, setModalProduct] = useState<Product | null | undefined>(undefined) // undefined = closed, null = create, Product = edit
  const [showImport, setShowImport] = useState(false)
  // CAJERO/GERENTE: id del producto cuya fila está expandida para editar PBS.
  const [expandedPbsProductId, setExpandedPbsProductId] = useState<string | null>(null)
  // Producto cuyo desglose por talla está abierto en la tabla.
  const [expandedVariantsId, setExpandedVariantsId] = useState<string | null>(null)
  // CAJERO/GERENTE: modal simplificado para crear producto.
  const [showMiniCreate, setShowMiniCreate] = useState(false)

  const LIMIT = 50

  const load = useCallback(async (q: string, dept: string, pg: number) => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { search: q, skip: pg * LIMIT, limit: LIMIT }
      if (dept) params.department_id = dept
      // CAJERO/GERENTE: NO enviamos branch_id ni active_in_branch — el backend
      // los deriva del JWT (defense in depth). Admins podrán usar un selector
      // de sucursal más adelante; por ahora ningún rol los envía desde aquí.
      const res = await productsApi.list(params)
      setProducts(res.items ?? [])
      setTotal(res.total ?? 0)
    } catch (e: any) {
      setProducts([])
      setTotal(0)
      const detail = e?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'No se pudo cargar el catálogo. Reintenta.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    productsApi.getDepartments()
      .then((d) => setDepartments(sortByName(d)))
      .catch(() => toast.error('No se pudieron cargar los departamentos.'))
    productsApi.getBrands()
      .then((b) => setBrands(sortByName(b)))
      .catch(() => toast.error('No se pudieron cargar las marcas.'))
  }, [])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setPage(0)
      load(search, deptId, 0)
    }, 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [search, deptId, load])

  // Refetch list whenever we navigate back to this page (e.g., after saving
  // a product in ProductForm). location.key changes on every navigation event,
  // so this fires on mount and on any return from a child route.
  const isFirstRender = useRef(true)
  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return }
    load(search, deptId, page)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key])

  const pages = Math.ceil(total / LIMIT)

  const openEdit = async (p: Product) => {
    // CAJERO/GERENTE con sucursal asignada: ruta al formulario dedicado.
    // El editor PBS inline sigue disponible vía el botón de sliders (⊟).
    if (BRANCH_EDIT_ROLES.includes(user?.role ?? '')) {
      if (!user?.branch_id) {
        toast.error('Tu usuario no tiene sucursal asignada. Contacta al administrador.')
        return
      }
      navigate(`/products/${p.id}/edit`)
      return
    }
    // Admin flow: cargar datos completos y abrir modal global.
    try {
      const full = await productsApi.getById(p.id)
      setModalProduct(full)
    } catch {
      toast.error('No se pudo cargar el detalle — mostrando datos básicos.')
      setModalProduct(p)
    }
  }

  const openBranchSettings = (p: Product) => {
    setViewMode('list')
    setExpandedPbsProductId(prev => (prev === p.id ? null : p.id))
  }

  const handleSaved = () => {
    setModalProduct(undefined)
    load(search, deptId, page)
  }

  /** Actualiza el producto en memoria con el PBS recién guardado, sin re-fetch. */
  const mergePbsIntoProduct = (productId: string, updated: ProductBranchStatus) => {
    setProducts(prev => prev.map(p => {
      if (p.id !== productId) return p
      const existing = p.branch_statuses ?? []
      const idx = existing.findIndex(s => s.id === updated.id || (s.variant_id === updated.variant_id && s.branch_id === updated.branch_id))
      const next = idx >= 0
        ? existing.map((s, i) => (i === idx ? updated : s))
        : [...existing, updated]
      return { ...p, branch_statuses: next }
    }))
  }

  const handleNewProductClick = () => {
    if (isBranchEditor) navigate('/products/new')
    else setModalProduct(null)
  }

  const handleMiniCreated = () => {
    setShowMiniCreate(false)
    load(search, deptId, page)
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-barcode text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">
            {isHQ ? 'Catálogo de Productos' : 'Consulta Productos'}
          </h1>
          {isHQ && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-violet-600/20 text-violet-400 border border-violet-500/30 rounded text-[9px] font-black uppercase tracking-widest">
              <i className="fa-solid fa-building-shield text-[8px]" /> HQ Global
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-slate-500 text-sm">{total.toLocaleString()} productos</span>
          {canEdit && (
            <>
              <button
                onClick={() => setShowImport(true)}
                className="dax-btn-secondary text-xs flex items-center gap-1.5"
              >
                <i className="fa-solid fa-file-import" /> Importar
              </button>
              <button
                onClick={handleNewProductClick}
                className="dax-btn text-xs flex items-center gap-1.5"
              >
                <i className="fa-solid fa-plus" /> Nuevo producto
              </button>
            </>
          )}
          <div className="flex items-center bg-slate-800 rounded-lg border border-slate-700/50 p-0.5">
            <button
              onClick={() => setViewMode('list')}
              className={`p-1.5 rounded-md transition-colors ${viewMode === 'list' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'}`}
              title="Vista lista"
            >
              <i className="fa-solid fa-list w-4 text-xs" />
            </button>
            <button
              onClick={() => setViewMode('grid')}
              className={`p-1.5 rounded-md transition-colors ${viewMode === 'grid' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'}`}
              title="Vista cuadrícula"
            >
              <i className="fa-solid fa-grip w-4 text-xs" />
            </button>
          </div>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex gap-3 flex-wrap">
        <input
          type="text"
          placeholder="Buscar por nombre o SKU..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="dax-input max-w-xs"
        />
        <select
          value={deptId}
          onChange={(e) => { setDeptId(e.target.value); setPage(0) }}
          className="dax-input max-w-[200px]"
        >
          <option value="">Todos los departamentos</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </div>

      {/* Tabla */}
      <DaxCard padding={false}>
        {loading ? (
          <Spinner text="Cargando productos..." />
        ) : products.length === 0 ? (
          <div className="p-12 text-center text-slate-600">Sin resultados</div>
        ) : viewMode === 'grid' ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 p-4">
            {products.map((p) => (
              <div key={p.id} className="bg-slate-800 rounded-xl p-3 flex flex-col gap-2 border border-slate-700/30 hover:border-indigo-500/30 transition-colors group relative">
                {p.image_url ? (
                  <img src={p.image_url} alt={p.name} className="w-full aspect-square object-contain rounded-lg bg-slate-700 p-1" />
                ) : (
                  <div className="w-full aspect-square bg-slate-700/50 rounded-lg flex items-center justify-center">
                    <i className="fa-solid fa-box text-slate-500 text-2xl" />
                  </div>
                )}
                <div className="flex-1">
                  <p className="text-white text-xs font-semibold line-clamp-2 leading-tight">{p.name}</p>
                  <p className="text-slate-500 text-[10px] font-mono mt-0.5">{p.sku}</p>
                  {p.department_name && <p className="text-slate-600 text-[10px] mt-0.5 truncate">{p.department_name}</p>}
                </div>
                <div className="flex items-center justify-between">
                  {(() => {
                    const rango = priceRange(p.variants ?? [])
                    return (
                      <span className="text-emerald-400 text-xs font-bold">
                        {rango && !rango.uniforme
                          ? `${formatCurrency(rango.min)} – ${formatCurrency(rango.max)}`
                          : formatCurrency(p.price ?? 0)}
                      </span>
                    )
                  })()}
                  {(() => {
                    const variantCount = p.variants?.length ?? 0
                    const qty = variantCount > 1
                      ? sumStock(p)
                      : (!isHQ && user?.branch_id && p.stock_levels?.length)
                        ? (p.stock_levels.find(s => s.branch_id === user.branch_id)?.qty_on_hand ?? p.stock ?? 0)
                        : (p.stock_total ?? p.stock ?? 0)
                    if (variantCount <= 1) {
                      return (
                        <span className={`dax-badge text-[10px] ${qty > 0 ? 'dax-badge-green' : 'dax-badge-red'}`}>
                          {qty}
                        </span>
                      )
                    }
                    const grupo = grupoDeVariantes(p.variants ?? [])
                    return (
                      <button
                        type="button"
                        // La cuadrícula no tiene dónde desplegar el desglose:
                        // se salta a la lista con ese producto ya abierto.
                        onClick={() => { setViewMode('list'); setExpandedVariantsId(p.id) }}
                        title={`Ver la existencia por ${SINGULAR_GRUPO[grupo]}`}
                        className="flex flex-col items-end group/tallas"
                      >
                        <span className={`dax-badge text-[10px] ${qty > 0 ? 'dax-badge-green' : 'dax-badge-red'}`}>
                          {qty}
                        </span>
                        <span className="text-slate-400 text-[10px] mt-0.5 group-hover/tallas:text-indigo-400">
                          de {variantCount} {grupo}
                        </span>
                      </button>
                    )
                  })()}
                </div>
                {canEdit && (
                  <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    {isBranchEditor && (
                      <button
                        onClick={() => openBranchSettings(p)}
                        className="w-6 h-6 rounded-full flex items-center justify-center bg-slate-700 border border-slate-600 hover:bg-indigo-600 hover:border-indigo-500"
                        title="Ajustes en mi sucursal"
                      >
                        <i className="fa-solid fa-sliders text-[9px] text-white" />
                      </button>
                    )}
                    <button
                      onClick={() => openEdit(p)}
                      className="w-6 h-6 rounded-full flex items-center justify-center bg-slate-700 border border-slate-600 hover:bg-indigo-600 hover:border-indigo-500"
                      title="Editar producto"
                    >
                      <i className="fa-solid fa-pencil text-[9px] text-white" />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Producto</th>
                  <th>Departamento</th>
                  <th className="text-right">Precio</th>
                  <th className="text-right">Stock</th>
                  <th>Estado</th>
                  {canEdit && <th />}
                </tr>
              </thead>
              <tbody>
                {products.map((p) => {
                  const isExpanded = isBranchEditor && expandedPbsProductId === p.id
                  const tallasAbiertas = expandedVariantsId === p.id && (p.variants?.length ?? 0) > 1
                  const colCount = 6 + (canEdit ? 1 : 0)
                  return (
                    <Fragment key={p.id}>
                      <tr>
                        <td className="font-mono text-slate-400 text-xs">{p.sku}</td>
                        <td>
                          <div className="flex items-center gap-2">
                            {p.image_url ? (
                              <img src={p.image_url} alt="" className="w-8 h-8 rounded object-cover flex-shrink-0" />
                            ) : (
                              <div className="w-8 h-8 rounded bg-slate-700 flex items-center justify-center flex-shrink-0">
                                <i className="fa-solid fa-box text-slate-500 text-xs" />
                              </div>
                            )}
                            <span className="font-medium text-white">{p.name}</span>
                          </div>
                        </td>
                        <td className="text-slate-400 text-xs">{p.department_name ?? '—'}</td>
                        <td className="text-right font-semibold text-emerald-400">
                          {(() => {
                            const override = user?.branch_id
                              ? p.branch_statuses?.find(s => s.branch_id === user.branch_id)?.price_override
                              : null
                            const effective = override != null ? override : (p.price ?? 0)
                            // Con varias tallas a distinto precio, un solo número miente:
                            // el de la fila era el de la principal. Se muestra el rango.
                            const rango = priceRange(p.variants ?? [])
                            const mostrarRango = override == null && rango != null && !rango.uniforme
                            return (
                              <div className="flex flex-col items-end leading-tight">
                                <span>
                                  {mostrarRango
                                    ? `${formatCurrency(rango!.min)} – ${formatCurrency(rango!.max)}`
                                    : formatCurrency(effective)}
                                </span>
                                {override != null && (
                                  <span className="text-[9px] text-indigo-400 font-normal">
                                    override (base {formatCurrency(p.price ?? 0)})
                                  </span>
                                )}
                                {mostrarRango && (
                                  <span className="text-[9px] text-slate-500 font-normal">
                                    según la {SINGULAR_GRUPO[grupoDeVariantes(p.variants ?? [])]}
                                  </span>
                                )}
                              </div>
                            )
                          })()}
                        </td>
                        <td className="text-right">
                          {(() => {
                            const variantCount = p.variants?.length ?? 0
                            // Con varias tallas la existencia del renglón es la SUMA:
                            // antes se veía solo la de la principal (3 de 12).
                            const qty = variantCount > 1
                              ? sumStock(p)
                              : (!isHQ && user?.branch_id && p.stock_levels?.length)
                                ? (p.stock_levels.find(s => s.branch_id === user.branch_id)?.qty_on_hand ?? p.stock ?? 0)
                                : (p.stock_total ?? p.stock ?? 0)
                            if (variantCount <= 1) {
                              return (
                                <span className={`dax-badge ${qty > 0 ? 'dax-badge-green' : 'dax-badge-red'}`}>
                                  {qty}
                                </span>
                              )
                            }
                            const grupo = grupoDeVariantes(p.variants ?? [])
                            return (
                              <button
                                type="button"
                                onClick={() => setExpandedVariantsId(tallasAbiertas ? null : p.id)}
                                aria-expanded={tallasAbiertas}
                                title={tallasAbiertas ? 'Ocultar el desglose' : `Ver la existencia por ${SINGULAR_GRUPO[grupo]}`}
                                className="flex flex-col items-end leading-tight ml-auto group/tallas"
                              >
                                <span className={`dax-badge ${qty > 0 ? 'dax-badge-green' : 'dax-badge-red'}`}>
                                  {qty}
                                </span>
                                <span className="text-slate-400 text-[10px] mt-0.5 group-hover/tallas:text-indigo-400">
                                  de {variantCount} {grupo}
                                  <i className={`fa-solid ${tallasAbiertas ? 'fa-chevron-up' : 'fa-chevron-down'} ml-1 text-[8px]`} />
                                </span>
                              </button>
                            )
                          })()}
                        </td>
                        <td>
                          {isHQ ? (
                            <span className="text-xs text-slate-400">
                              {p.branch_statuses?.filter(s => s.is_active_pos).length ?? 0}
                              <span className="text-slate-600 ml-0.5">sucursales</span>
                            </span>
                          ) : user?.branch_id ? (
                            (() => {
                              const status = p.branch_statuses?.find(s => s.branch_id === user.branch_id)
                              if (!status) return <span className="text-[10px] text-slate-600 italic">Global</span>
                              return status.is_active_pos
                                ? <Badge variant="green">POS activo</Badge>
                                : <Badge variant="red">POS inactivo</Badge>
                            })()
                          ) : null}
                        </td>
                        {canEdit && (
                          <td className="text-right">
                            <div className="inline-flex items-center gap-1">
                              {isBranchEditor && (
                                <button
                                  onClick={() => openBranchSettings(p)}
                                  className={`transition-colors p-1 ${isExpanded ? 'text-indigo-400' : 'text-slate-500 hover:text-indigo-400'}`}
                                  title={isExpanded ? 'Cerrar ajustes de sucursal' : 'Ajustes en mi sucursal'}
                                >
                                  <i className={`fa-solid ${isExpanded ? 'fa-chevron-up' : 'fa-sliders'} text-xs`} />
                                </button>
                              )}
                              <button
                                onClick={() => openEdit(p)}
                                className="transition-colors p-1 text-slate-500 hover:text-indigo-400"
                                title="Editar producto"
                              >
                                <i className="fa-solid fa-pencil text-xs" />
                              </button>
                            </div>
                          </td>
                        )}
                      </tr>
                      {tallasAbiertas && expandVariantRows([p]).map((row) => (
                        <tr key={row.variant.id} className="bg-slate-900/40 text-xs">
                          <td className="font-mono text-slate-500 pl-6">{row.sku}</td>
                          <td className="text-slate-300">
                            <i className="fa-solid fa-turn-up fa-rotate-90 text-slate-600 mr-2 text-[10px]" />
                            {nombreDeVariante(p, row.variant)}
                          </td>
                          <td />
                          <td className="text-right text-emerald-400/80">{formatCurrency(row.variant.price ?? 0)}</td>
                          <td className={`text-right font-semibold ${row.qty > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {row.qty}
                          </td>
                          <td colSpan={colCount - 5} />
                        </tr>
                      ))}
                      {isExpanded && user?.branch_id != null && (
                        <tr className="bg-slate-900/40">
                          <td colSpan={colCount} className="px-4 py-3">
                            <BranchStatusEditor
                              product={p}
                              branchId={user.branch_id}
                              onSaved={(updated) => {
                                mergePbsIntoProduct(p.id, updated)
                                setExpandedPbsProductId(null)
                              }}
                              onCancel={() => setExpandedPbsProductId(null)}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Paginación */}
        {pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700/50">
            <button
              onClick={() => { const np = page - 1; setPage(np); load(search, deptId, np) }}
              disabled={page === 0}
              className="dax-btn-secondary text-xs disabled:opacity-40"
            >
              ← Anterior
            </button>
            <span className="text-slate-500 text-xs">Página {page + 1} de {pages}</span>
            <button
              onClick={() => { const np = page + 1; setPage(np); load(search, deptId, np) }}
              disabled={page >= pages - 1}
              className="dax-btn-secondary text-xs disabled:opacity-40"
            >
              Siguiente →
            </button>
          </div>
        )}
      </DaxCard>

      {/* Modales */}
      {showImport && (
        <ImportModal
          isHQ={isHQ}
          onClose={() => setShowImport(false)}
          onDone={() => { setShowImport(false); load(search, deptId, page) }}
        />
      )}
      {/* Modal global de edición (solo para admin / DUEÑO; CAJERO/GERENTE usan inline). */}
      {!isBranchEditor && modalProduct !== undefined && (
        <ProductModal
          product={modalProduct}
          onClose={() => setModalProduct(undefined)}
          onSaved={handleSaved}
          brands={brands}
          departments={departments}
          isCajero={user?.role === 'CAJERO'}
        />
      )}
      {/* Modal simplificado de creación para CAJERO/GERENTE. */}
      {showMiniCreate && (
        <CreateProductMiniModal
          brands={brands}
          departments={departments}
          onClose={() => setShowMiniCreate(false)}
          onCreated={handleMiniCreated}
        />
      )}
    </div>
  )
}
