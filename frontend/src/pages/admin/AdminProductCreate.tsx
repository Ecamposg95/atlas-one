import { useEffect, useState } from 'react'
import { fieldErrorsFromDetail, summarizeFieldErrors } from '../../utils/apiErrors'
import { useNavigate } from 'react-router-dom'
import { productsApi } from '../../api/products'
import { organizationApi } from '../../api/organization'
import { sortByName } from '../../utils/sortByName'
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
import {
  splitPrincipal, toExtraVariants, variantDetailErrors, variantFieldErrors, type VariantRow,
} from '../../components/products/variantMatrix'

export function AdminProductCreate() {
  const navigate = useNavigate()

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

  useEffect(() => {
    let cancelled = false
    Promise.all([
      productsApi.getDepartments(),
      productsApi.getBrands(),
      organizationApi.getBranches(),
    ])
      .then(([depts, brs, bchs]) => {
        if (cancelled) return
        setDepartments(sortByName(depts))
        setBrands(sortByName(brs))
        setBranches(bchs)
        const init: Record<number, BranchActivation> = {}
        for (const b of bchs) {
          init[b.id] = { enabled: false, is_active_pos: true, is_active_hq: false, is_visible: true }
        }
        setBranchActivation(init)
      })
      .catch(() => toast.error('No se pudo cargar el formulario.'))
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

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

  const enabledBranchIds = Object.entries(branchActivation)
    .filter(([, v]) => v.enabled)
    .map(([k]) => Number(k))

  // Existencia inicial total del alta: la de la principal (campo de arriba)
  // mas la que trae cada talla hermana en la matriz.
  const stockHermanas = splitPrincipal(hasVariantsModule ? variantRows : []).extras
    .reduce((acc, r) => acc + (Number(r.initial_stock) || 0), 0)
  const totalInicial = (Number(form.initial_stock || '0') || 0) + stockHermanas
  const sucursalStock = branches.find((b) => b.id === Number(form.initial_stock_branch_id)) ?? null

  const validate = (): ProductErrors => {
    const e: ProductErrors = {}
    if (!form.name.trim()) e.name = 'Requerido'
    if (!form.sku.trim()) e.sku = 'Requerido'
    const priceNum = Number(form.price)
    const costNum = Number(form.cost)
    if (!Number.isFinite(priceNum) || priceNum < 0) e.price = 'Número ≥ 0'
    if (!Number.isFinite(costNum) || costNum < 0) e.cost = 'Número ≥ 0'
    const stockNum = Number(form.initial_stock || '0')
    if (!Number.isFinite(stockNum) || stockNum < 0) e.initial_stock = 'Número ≥ 0'
    // La existencia inicial se reparte por talla: la sucursal destino hace
    // falta si CUALQUIERA de las filas trae existencia, no solo la principal.
    if (totalInicial > 0 && !form.initial_stock_branch_id)
      e.initial_stock_branch_id = 'Requerido con existencia inicial'
    if (enabledBranchIds.length === 0) e.target_branch_ids = 'Activa al menos una sucursal'
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
      // La sucursal destino viaja si CUALQUIER talla trae existencia: sin ella
      // el backend no sabria donde meter la de las hermanas.
      branch_id: totalInicial > 0 ? Number(form.initial_stock_branch_id) : null,
      target_branch_ids: enabledBranchIds,
      uses_inventory: true,
      prices: prices.map((p) => ({
        price_name: p.price_name,
        min_quantity: Number(p.min_quantity),
        unit_price: Number(p.unit_price),
      })),
      ...variantPayload,
    }
    try {
      await productsApi.create(payload)
      toast.success('Producto creado.')
      navigate('/admin/catalog')
    } catch (err: any) {
      const status = err?.response?.status
      const detail = err?.response?.data?.detail
      // Un 409 de la matriz (SKU o código repetido de una talla) cita la fila
      // culpable: marcarla ahí en vez de acusar al SKU base del producto.
      const porFila = variantDetailErrors(detail, splitPrincipal(variantRows).extras)
      if (Object.keys(porFila).length > 0) {
        setErrors((e) => ({ ...e, ...porFila }))
        toast.error('Revisa la variante marcada.')
      } else if (status === 409 || (typeof detail === 'string' && detail.toLowerCase().includes('sku'))) {
        setErrors((e) => ({ ...e, sku: typeof detail === 'string' ? detail : 'SKU duplicado' }))
      }
      // Un 422 trae `detail` como LISTA de campos. Antes se caia al mensaje
      // generico y el usuario no sabia que corregir.
      const porCampo = variantFieldErrors(fieldErrorsFromDetail(detail))
      if (Object.keys(porCampo).length > 0) {
        setErrors((prev) => ({ ...prev, ...porCampo }))
        toast.error(summarizeFieldErrors(porCampo))
      } else {
        toast.error(typeof detail === 'string' ? detail : 'No se pudo crear el producto.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Spinner size="lg" /></div>
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <i className="fa-solid fa-plus text-indigo-400 text-xl" />
        <h1 className="text-2xl font-black text-white">Nuevo producto — Administración</h1>
      </div>
      <DaxCard>
        <div className="p-4 space-y-6">
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
          {hasVariantsModule && (
            <ProductVariantsSection
              baseSku={form.sku} rows={variantRows} onRowsChange={setVariantRows} firstIsPrincipal
              errors={errors} showInitialStock
              principalStock={form.initial_stock}
              onPrincipalStockChange={(v) => setField('initial_stock', v)}
              stockBranchName={sucursalStock?.name ?? null}
            />
          )}
          <ProductBranchMatrixSection
            branches={branches} activation={branchActivation}
            onToggle={toggleBranch} onSetAll={setAllBranches} errors={errors}
          />
          <ProductInitialStockSection
            value={form} onChange={setField} errors={errors}
            branches={branches} enabledBranchIds={enabledBranchIds}
            perVariantTotal={hasVariantsModule && variantRows.length > 0 ? totalInicial : null}
            footer="Para stock en múltiples sucursales, usa el módulo de inventario tras crear."
          />

          <p className="text-[11px] text-slate-500">
            Precios escalonados y empaques se configuran desde el catálogo tras crear el producto.
          </p>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800/60">
            <button type="button" className="dax-btn-secondary text-xs"
              onClick={() => navigate('/admin/catalog')} disabled={submitting}>
              Cancelar
            </button>
            <button type="button" className="dax-btn-primary text-xs inline-flex items-center gap-1.5"
              onClick={handleSubmit} disabled={submitting}>
              {submitting ? <Spinner size="sm" /> : <i className="fa-solid fa-save" />}
              Crear producto
            </button>
          </div>
        </div>
      </DaxCard>
    </div>
  )
}
