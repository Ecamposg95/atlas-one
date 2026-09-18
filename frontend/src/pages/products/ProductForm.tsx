import { useEffect, useState } from 'react'
import { fieldErrorsFromDetail, summarizeFieldErrors } from '../../utils/apiErrors'
import { useNavigate, useParams } from 'react-router-dom'
import { productsApi } from '../../api/products'
import { organizationApi } from '../../api/organization'
import { sortByName } from '../../utils/sortByName'
import { useAuthStore } from '../../store/authStore'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { toast } from '../../store/toastStore'
import { ProductBasicsSection } from '../../components/products/ProductBasicsSection'
import { ProductCommercialSection } from '../../components/products/ProductCommercialSection'
import { ProductBranchMatrixSection } from '../../components/products/ProductBranchMatrixSection'
import { ProductInitialStockSection } from '../../components/products/ProductInitialStockSection'
import { ProductTieredPricesSection } from '../../components/products/ProductTieredPricesSection'
import {
  EMPTY_PRODUCT_FORM,
  type BranchActivation,
  type Brand,
  type Branch,
  type Department,
  type PriceRow,
  type ProductErrors,
  type ProductFormValue,
} from '../../components/products/types'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { ProductVariantsSection } from '../../components/products/ProductVariantsSection'
import { ProductVariantsEditor } from '../../components/products/ProductVariantsEditor'
import { splitPrincipal, toExtraVariants, variantFieldErrors, type VariantRow } from '../../components/products/variantMatrix'
import { variantLabel } from '../../components/products/variantWords'
import type { Product } from '../../types/products'

const ADMIN_ROLES = new Set(['ADMINISTRADOR', 'DUEÑO'])

export function ProductForm() {
  const navigate = useNavigate()
  const { id } = useParams<{ id?: string }>()
  const mode: 'create' | 'edit' = id ? 'edit' : 'create'
  const { user } = useAuthStore()
  const isAdmin = user ? ADMIN_ROLES.has(user.role) : false
  const userBranchId = user?.branch_id ?? null

  const [departments, setDepartments] = useState<Department[]>([])
  const [brands, setBrands] = useState<Brand[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  const [form, setForm] = useState<ProductFormValue>(EMPTY_PRODUCT_FORM)
  const [branchActivation, setBranchActivation] = useState<Record<number, BranchActivation>>({})
  const [prices, setPrices] = useState<PriceRow[]>([])
  const [errors, setErrors] = useState<ProductErrors>({})
  const hasVariantsModule = useEnabledModulesStore((s) => s.enabledModules.includes('variants'))
  const [variantRows, setVariantRows] = useState<VariantRow[]>([])
  const [loaded, setLoaded] = useState<Product | null>(null)

  useEffect(() => {
    let cancelled = false
    const loaders: Promise<unknown>[] = [
      productsApi.getDepartments().then((d) => { if (!cancelled) setDepartments(sortByName(d)) }),
      productsApi.getBrands().then((b) => { if (!cancelled) setBrands(sortByName(b)) }),
    ]
    // Admin necesita la lista de sucursales para la matriz; cajero solo la propia.
    if (isAdmin) {
      loaders.push(organizationApi.getBranches().then((bchs) => {
        if (cancelled) return
        setBranches(bchs)
        const init: Record<number, BranchActivation> = {}
        for (const b of bchs) {
          init[b.id] = { enabled: false, is_active_pos: true, is_active_hq: false, is_visible: true }
        }
        setBranchActivation(init)
      }))
    } else if (userBranchId && user?.branch_name) {
      // Sintetizamos una Branch mínima para poder mostrar el nombre en la sección de stock.
      setBranches([{ id: userBranchId, name: user.branch_name, branch_type: 'STORE', is_headquarters: false }])
    }
    // Edit mode: precarga el producto.
    if (mode === 'edit' && id) {
      loaders.push(productsApi.getById(id).then((p) => {
        if (cancelled) return
        setLoaded(p)
        const v = p.variants?.[0]
        setForm({
          name: p.name ?? '',
          sku: p.sku ?? '',
          barcode: (v?.barcode ?? p.barcode ?? '') as string,
          unit: p.unit ?? 'pza',
          description: p.description ?? '',
          image_url: p.image_url ?? '',
          department_id: (p.department?.id ?? '') as string,
          brand_id: (p.brand_id ?? '') as string,
          price: String(v?.price ?? p.price ?? ''),
          cost: String(v?.cost ?? p.cost ?? ''),
          has_iva: Boolean(v?.has_iva ?? p.has_iva ?? false),
          tax_rate: String(v?.tax_rate ?? p.tax_rate ?? '16'),
          initial_stock: '0',
          initial_stock_branch_id: '',
        })
        // Precios escalonados: variante principal o top-level como fallback.
        const tierSrc = v?.prices ?? p.prices ?? []
        setPrices(tierSrc.map((tp) => ({
          id: tp.id,
          price_name: tp.price_name,
          min_quantity: Number(tp.min_quantity),
          unit_price: Number(tp.unit_price),
        })))
      }))
    }

    Promise.all(loaders)
      .catch(() => { if (!cancelled) toast.error('No se pudo cargar el formulario.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [mode, id, isAdmin, userBranchId, user?.branch_name])

  const setField = <K extends keyof ProductFormValue>(key: K, value: ProductFormValue[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
    if (errors[key as string]) setErrors((e) => { const { [key as string]: _, ...rest } = e; return rest })
  }

  const toggleBranch = (branchId: number, patch: Partial<BranchActivation>) => {
    setBranchActivation((prev) => ({ ...prev, [branchId]: { ...prev[branchId], ...patch } }))
    if (patch.enabled === false && Number(form.initial_stock_branch_id) === branchId) {
      setForm((f) => ({ ...f, initial_stock_branch_id: '' }))
    }
  }

  const setAllBranches = (enabled: boolean) => {
    setBranchActivation((prev) => {
      const next: Record<number, BranchActivation> = {}
      for (const id of Object.keys(prev)) {
        next[Number(id)] = { ...prev[Number(id)], enabled }
      }
      return next
    })
    if (!enabled) setForm((f) => ({ ...f, initial_stock_branch_id: '' }))
  }

  // Para admin: las sucursales marcadas en la matriz. Para cajero: su sucursal.
  const enabledBranchIds = isAdmin
    ? Object.entries(branchActivation).filter(([, v]) => v.enabled).map(([k]) => Number(k))
    : (userBranchId ? [userBranchId] : [])

  // Existencia inicial total del alta: la de la principal (campo de arriba)
  // mas la que trae cada talla hermana en la matriz.
  const stockHermanas = splitPrincipal(hasVariantsModule ? variantRows : []).extras
    .reduce((acc, r) => acc + (Number(r.initial_stock) || 0), 0)
  const totalInicial = (Number(form.initial_stock || '0') || 0) + stockHermanas
  const sucursalStock = isAdmin
    ? branches.find((b) => b.id === Number(form.initial_stock_branch_id)) ?? null
    : branches.find((b) => b.id === userBranchId) ?? null

  const validate = (): ProductErrors => {
    const e: ProductErrors = {}
    if (!form.name.trim()) e.name = 'Requerido'
    if (!form.sku.trim()) e.sku = 'Requerido'
    const priceNum = Number(form.price)
    const costNum = Number(form.cost)
    if (!Number.isFinite(priceNum) || priceNum < 0) e.price = 'Número ≥ 0'
    if (!Number.isFinite(costNum) || costNum < 0) e.cost = 'Número ≥ 0'
    if (mode === 'create') {
      const stockNum = Number(form.initial_stock || '0')
      if (!Number.isFinite(stockNum) || stockNum < 0) e.initial_stock = 'Número ≥ 0'
      if (isAdmin) {
        // Admin: matriz debe tener al menos una sucursal activa.
        if (enabledBranchIds.length === 0) e.target_branch_ids = 'Activa al menos una sucursal'
        // La existencia se reparte por talla: la sucursal hace falta si
        // cualquiera de las filas trae existencia, no solo la principal.
        if (totalInicial > 0 && !form.initial_stock_branch_id)
          e.initial_stock_branch_id = 'Requerido con existencia inicial'
      } else {
        // Cajero: sucursal implícita; solo validar que esté asignada.
        if (!userBranchId) e.target_branch_ids = 'Tu usuario no tiene sucursal asignada'
      }
    }
    // Los renglones de precios extra (Mayoreo, Caja) no se validaban: un valor
    // no numerico llegaba al backend como null y volvia un 422 que la pantalla
    // mostraba como "no se pudo", sin decir cual campo.
    prices.forEach((p, i) => {
      if (!p.price_name.trim()) e[`prices.${i}.price_name`] = 'Requerido'
      if (!Number.isFinite(Number(p.min_quantity)) || Number(p.min_quantity) <= 0)
        e[`prices.${i}.min_quantity`] = 'Cantidad mínima mayor a 0'
      if (!Number.isFinite(Number(p.unit_price)) || Number(p.unit_price) < 0)
        e[`prices.${i}.unit_price`] = 'Número ≥ 0'
    })
    if (form.has_iva && !Number.isFinite(Number(form.tax_rate)))
      e.tax_rate = 'Escribe un número'
    if (mode === 'create') {
      // La primera fila es la principal: su SKU es el base, no se valida aparte.
      const skus = new Set<string>([form.sku.trim().toLowerCase()])
      splitPrincipal(variantRows).extras.forEach((r, i) => {
        const s = r.sku.trim().toLowerCase()
        if (!s) e[`variants.${i}.sku`] = 'SKU requerido'
        else if (skus.has(s)) e[`variants.${i}.sku`] = 'SKU repetido'
        skus.add(s)
        if (r.price.trim() && !(Number(r.price) > 0)) e[`variants.${i}.price`] = 'Precio mayor a 0'
        const st = Number(r.initial_stock)
        if (r.initial_stock.trim() && !(Number.isFinite(st) && st >= 0))
          e[`variants.${i}.initial_stock`] = 'Número ≥ 0'
      })
    }
    return e
  }

  const handleSubmit = async () => {
    const clientErrors = validate()
    if (Object.keys(clientErrors).length > 0) {
      setErrors(clientErrors)
      toast.error('Revisa los campos marcados.')
      return
    }
    setSubmitting(true)
    try {
      if (mode === 'create') {
        const stockNum = Number(form.initial_stock || '0')
        // Matriz boutique: la primera combinación ES la variante principal
        // (`color`/`size` del producto); el resto viajan como `extra_variants`.
        const { principal, extras } = splitPrincipal(hasVariantsModule ? variantRows : [])
        const variantPayload = principal
          ? {
              ...(principal.color ? { color: principal.color } : {}),
              ...(principal.size ? { size: principal.size } : {}),
              ...(extras.length > 0 ? { extra_variants: toExtraVariants(extras) } : {}),
            }
          : {}
        // La sucursal destino viaja si CUALQUIER talla trae existencia: sin
        // ella el backend no sabria donde meter la de las hermanas.
        const initialStockBranchId = isAdmin
          ? (totalInicial > 0 ? Number(form.initial_stock_branch_id) : null)
          : (totalInicial > 0 ? userBranchId : null)
        const payload = {
          name: form.name.trim(),
          sku: form.sku.trim(),
          barcode: form.barcode.trim() || null,
          unit: form.unit,
          description: form.description.trim() || null,
          image_url: form.image_url.trim() || null,
          department_id: form.department_id || null,
          brand_id: form.brand_id || null,
          price: Number(form.price),
          cost: Number(form.cost),
          has_iva: form.has_iva,
          tax_rate: form.has_iva ? Number(form.tax_rate) : 0,
          initial_stock: stockNum,
          branch_id: initialStockBranchId,
          target_branch_ids: enabledBranchIds,
          uses_inventory: true,
          prices: prices.map((p) => ({
            price_name: p.price_name,
            min_quantity: Number(p.min_quantity),
            unit_price: Number(p.unit_price),
          })),
          ...variantPayload,
        }
        await productsApi.create(payload)
        toast.success('Producto creado.')
        navigate('/products')
      } else if (id) {
        // Edit: solo campos del producto; no se tocan matriz ni stock inicial.
        const payload = {
          name: form.name.trim(),
          sku: form.sku.trim(),
          barcode: form.barcode.trim() || null,
          unit: form.unit,
          description: form.description.trim() || null,
          image_url: form.image_url.trim() || null,
          department_id: form.department_id || null,
          brand_id: form.brand_id || null,
          price: Number(form.price),
          cost: Number(form.cost),
          has_iva: form.has_iva,
          tax_rate: form.has_iva ? Number(form.tax_rate) : 0,
          prices: prices.map((p) => ({
            price_name: p.price_name,
            min_quantity: Number(p.min_quantity),
            unit_price: Number(p.unit_price),
          })),
        }
        await productsApi.update(id, payload)
        toast.success('Producto actualizado.')
        navigate('/products')
      }
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { detail?: string } } }
      const status = e?.response?.status
      const detail = e?.response?.data?.detail
      if (status === 409 || (typeof detail === 'string' && detail.toLowerCase().includes('sku'))) {
        setErrors((prev) => ({ ...prev, sku: typeof detail === 'string' ? detail : 'SKU duplicado' }))
      }
      // Un 422 trae `detail` como LISTA de campos. Antes se caia al mensaje
      // generico y el usuario no sabia que corregir.
      const porCampo = variantFieldErrors(fieldErrorsFromDetail(detail))
      if (Object.keys(porCampo).length > 0) {
        setErrors((prev) => ({ ...prev, ...porCampo }))
        toast.error(summarizeFieldErrors(porCampo))
      } else {
        toast.error(typeof detail === 'string' ? detail : `No se pudo ${mode === 'create' ? 'crear' : 'actualizar'} el producto.`)
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Spinner size="lg" /></div>
  }

  // Aviso #15: arriba de Básicos y dicho como lo diría la dueña — estos
  // campos son los de la PRIMERA talla, no los del producto entero.
  const principalCargada = mode === 'edit' && hasVariantsModule && loaded && (loaded.variants?.length ?? 0) > 1
    ? loaded.variants![0]
    : null
  const avisoPrincipal = principalCargada
    ? `Nombre, precio y código de aquí son los de la talla ${variantLabel(principalCargada, loaded?.name ?? '')}. Las demás tallas, abajo.`
    : null

  const title = mode === 'create' ? 'Nuevo producto' : 'Editar producto'
  const iconCls = mode === 'create' ? 'fa-solid fa-plus' : 'fa-solid fa-pen-to-square'
  const cta = mode === 'create' ? 'Crear producto' : 'Guardar cambios'

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <i className={`${iconCls} text-indigo-400 text-xl`} />
        <h1 className="text-2xl font-black text-white">{title}</h1>
        {!isAdmin && user?.branch_name && (
          <span className="text-xs text-slate-500">· sucursal {user.branch_name}</span>
        )}
      </div>
      <DaxCard>
        <div className="p-4 space-y-6">
          {avisoPrincipal && (
            <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
              {avisoPrincipal}
            </p>
          )}
          <ProductBasicsSection value={form} onChange={setField} errors={errors} />
          <ProductCommercialSection
            value={form} onChange={setField} errors={errors}
            departments={departments} brands={brands}
          />
          <ProductTieredPricesSection
            prices={prices}
            onChange={setPrices}
            errors={errors}
            help="Para precios por cantidad (mayoreo, promo). Se aplica sobre el precio base."
          />
          {mode === 'create' && hasVariantsModule && (
            <ProductVariantsSection
              baseSku={form.sku} rows={variantRows} onRowsChange={setVariantRows} firstIsPrincipal
              errors={errors} showInitialStock
              principalStock={form.initial_stock}
              onPrincipalStockChange={(v) => setField('initial_stock', v)}
              stockBranchName={sucursalStock?.name ?? null}
            />
          )}
          {mode === 'create' && isAdmin && (
            <ProductBranchMatrixSection
              branches={branches} activation={branchActivation}
              onToggle={toggleBranch} onSetAll={setAllBranches} errors={errors}
            />
          )}
          {mode === 'create' && (
            <ProductInitialStockSection
              value={form} onChange={setField} errors={errors}
              branches={branches} enabledBranchIds={enabledBranchIds}
              lockedBranchId={!isAdmin && userBranchId ? userBranchId : undefined}
              perVariantTotal={hasVariantsModule && variantRows.length > 0 ? totalInicial : null}
              footer={isAdmin
                ? 'Para stock en múltiples sucursales, usa el módulo de inventario tras crear.'
                : 'El stock se aplica a tu sucursal.'}
            />
          )}
          {mode === 'edit' && hasVariantsModule && loaded && (
            <ProductVariantsEditor product={loaded} onChanged={setLoaded} />
          )}

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800/60">
            <button type="button" className="dax-btn-secondary text-xs"
              onClick={() => navigate('/products')} disabled={submitting}>
              Cancelar
            </button>
            <button type="button" className="dax-btn-primary text-xs inline-flex items-center gap-1.5"
              onClick={handleSubmit} disabled={submitting}>
              {submitting ? <Spinner size="sm" /> : <i className="fa-solid fa-save" />}
              {cta}
            </button>
          </div>
        </div>
      </DaxCard>
    </div>
  )
}
