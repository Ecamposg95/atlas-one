import { useEffect, useState } from 'react'
import { productsApi } from '../../api/products'
import { organizationApi } from '../../api/organization'
import { sortByName } from '../../utils/sortByName'
import { useAuthStore } from '../../store/authStore'
import { useCamposProducto, useEnabledModulesStore, useModoBasico } from '../../store/enabledModulesStore'
import { DaxCard } from '../ui/DaxCard'
import { Spinner } from '../ui/Spinner'
import { toast } from '../../store/toastStore'
import { confirm } from '../ui/ConfirmDialog'
import { ProductBasicsSection } from './ProductBasicsSection'
import { ProductCommercialSection } from './ProductCommercialSection'
import { ProductTieredPricesSection } from './ProductTieredPricesSection'
import { ProductPackagingSection } from './ProductPackagingSection'
import { ProductVariantsSection } from './ProductVariantsSection'
import { ProductVariantsEditor } from './ProductVariantsEditor'
import { ProductBranchMatrixSection } from './ProductBranchMatrixSection'
import { ProductInitialStockSection } from './ProductInitialStockSection'
import { ProductImageUploader } from './ProductImageUploader'
import { campoVisible } from './camposProducto'
import {
  EMPTY_PRODUCT_FORM, type BranchActivation, type Brand, type Branch, type Department,
  type PackagingRow, type PriceRow, type ProductErrors, type ProductFormValue,
} from './types'
import { type VariantRow } from './variantMatrix'
import { esFilaPrincipal } from '../branch/variantEdit'
import { variantLabel } from './variantWords'
import { argsSugerencia, mensajeSugerencia } from './skuSuggest'
import {
  armarPayloadAlta, armarPayloadEdicion, erroresDeApi, formDesdeProducto, precioATodasPorDefecto, principalCambio, totalInicial, validarProducto,
  type EntradaFormulario,
} from './productoForm'
import type { Product } from '../../types/products'

const ADMIN_ROLES = new Set(['ADMINISTRADOR', 'DUEÑO'])

export interface FormularioProductoProps {
  mode: 'create' | 'edit'
  /** Obligatorio en edición: el formulario carga el producto con GET /products/{id}. */
  productId?: string
  /** Talla de la que salió el renglón (lista de sucursal). */
  variantId?: string
  /** 'pagina' pinta encabezado y tarjeta; 'modal' solo el contenido (el título lo pone el Modal). */
  presentacion: 'pagina' | 'modal'
  onDone: (producto: Product) => void
  onCancel: () => void
}

/**
 * El único formulario de producto (mega plan SP1): alta y edición para
 * admin, gerente y cajero, como página o dentro de un Modal. Toda la lógica
 * de validación y payload vive en `productoForm.ts`.
 */
export function FormularioProducto({ mode, productId, variantId, presentacion, onDone, onCancel }: FormularioProductoProps) {
  const { user } = useAuthStore()
  const isAdmin = user ? ADMIN_ROLES.has(user.role) : false
  const userBranchId = user?.branch_id ?? null
  const hasVariantsModule = useEnabledModulesStore((s) => s.enabledModules.includes('variants'))
  const campos = useCamposProducto()
  const modoBasico = useModoBasico()

  const [departments, setDepartments] = useState<Department[]>([])
  const [brands, setBrands] = useState<Brand[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  const [form, setForm] = useState<ProductFormValue>(EMPTY_PRODUCT_FORM)
  const [branchActivation, setBranchActivation] = useState<Record<number, BranchActivation>>({})
  const [prices, setPrices] = useState<PriceRow[]>([])
  const [packagings, setPackagings] = useState<PackagingRow[]>([])
  const [errors, setErrors] = useState<ProductErrors>({})
  // El precio de la ficha es el de la talla principal; con la casilla (y si el precio cambió) baja a todas.
  const [precioATodas, setPrecioATodas] = useState(false)
  const [variantRows, setVariantRows] = useState<VariantRow[]>([])
  const [loaded, setLoaded] = useState<Product | null>(null)
  const [sugiriendoSku, setSugiriendoSku] = useState(false)

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
        // Modo básico con una sola sucursal: la matriz no se pinta, así que la
        // sucursal va marcada y es el destino de la existencia inicial.
        const unica = modoBasico && bchs.length === 1
        const init: Record<number, BranchActivation> = {}
        for (const b of bchs) init[b.id] = { enabled: unica, is_active_pos: true, is_active_hq: false, is_visible: true }
        setBranchActivation(init)
        if (unica && mode === 'create') setForm((f) => ({ ...f, initial_stock_branch_id: String(bchs[0].id) }))
      }))
    } else if (userBranchId && user?.branch_name) {
      // Branch mínima para poder mostrar el nombre en la sección de existencia.
      setBranches([{ id: userBranchId, name: user.branch_name, branch_type: 'STORE', is_headquarters: false }])
    }
    if (mode === 'edit') {
      if (!productId) { onCancel(); return () => { cancelled = true } }
      // Sin el detalle completo no se edita: un PUT armado desde la fila de la
      // lista (sin empaques ni escalones) los borraría al reemplazarlos.
      loaders.push(productsApi.getById(productId).then((p) => {
        if (cancelled) return
        setLoaded(p)
        const estado = formDesdeProducto(p, variantId)
        // La casilla arranca marcada solo si todas las tallas ya comparten el
        // precio de la principal (ver precioATodasPorDefecto).
        setPrecioATodas(precioATodasPorDefecto(p, variantId, hasVariantsModule))
        setForm(estado.form); setPrices(estado.prices); setPackagings(estado.packagings)
      }).catch(() => {
        if (cancelled) return
        toast.error('No se pudo cargar el producto.')
        onCancel()
      }))
    }
    Promise.all(loaders)
      .catch(() => { if (!cancelled) toast.error('No se pudo cargar el formulario.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, productId, variantId, isAdmin, userBranchId, user?.branch_name, modoBasico])

  const setField = <K extends keyof ProductFormValue>(key: K, value: ProductFormValue[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
    if (errors[key as string]) setErrors((e) => { const { [key as string]: _, ...rest } = e; return rest })
  }

  /** Pide el SKU de la familia y lo aplica SOLO si el usuario acepta. */
  const sugerirSku = async () => {
    if (!form.name.trim()) { setErrors((e) => ({ ...e, name: 'Escribe el nombre antes de sugerir el SKU' })); return }
    setSugiriendoSku(true)
    try {
      const { sku, available } = await productsApi.skuSuggest(argsSugerencia(form, brands))
      if (!sku) { toast.error('Faltan datos para sugerir un SKU.'); return }
      const ok = await confirm({
        title: 'Usar el SKU sugerido',
        message: <span style={{ whiteSpace: 'pre-line' }}>{mensajeSugerencia(sku, available, form.sku)}</span>,
        confirmText: 'Usar este SKU',
        variant: available ? 'info' : 'warning',
      })
      if (ok) setField('sku', sku)
    } catch {
      toast.error('No se pudo sugerir el SKU.')
    } finally {
      setSugiriendoSku(false)
    }
  }

  /** El editor de tallas devuelve el producto; si cambió la principal se re-sincroniza su identidad. */
  const alCambiarTallas = (p: Product) => {
    if (principalCambio(loaded, p, variantId)) {
      const { form: nuevo } = formDesdeProducto(p, variantId)
      // Solo la identidad/precio de la talla: nombre y descripción pueden estar editados.
      setForm((f) => ({
        ...f, sku: nuevo.sku, barcode: nuevo.barcode, price: nuevo.price, cost: nuevo.cost,
        has_iva: nuevo.has_iva, tax_rate: nuevo.tax_rate,
      }))
      setPrecioATodas(precioATodasPorDefecto(p, variantId, hasVariantsModule))
    }
    setLoaded(p)
  }

  const toggleBranch = (branchId: number, patch: Partial<BranchActivation>) => {
    setBranchActivation((prev) => ({ ...prev, [branchId]: { ...prev[branchId], ...patch } }))
    if (patch.enabled === false && Number(form.initial_stock_branch_id) === branchId) setField('initial_stock_branch_id', '')
  }
  const setAllBranches = (enabled: boolean) => {
    setBranchActivation((prev) => Object.fromEntries(Object.entries(prev).map(([k, v]) => [k, { ...v, enabled }])))
    if (!enabled) setField('initial_stock_branch_id', '')
  }

  const enabledBranchIds = isAdmin
    ? Object.entries(branchActivation).filter(([, v]) => v.enabled).map(([k]) => Number(k))
    : (userBranchId ? [userBranchId] : [])
  const total = totalInicial(form, variantRows, hasVariantsModule)
  const sucursalStock = isAdmin
    ? branches.find((b) => b.id === Number(form.initial_stock_branch_id)) ?? null
    : branches.find((b) => b.id === userBranchId) ?? null

  const handleSubmit = async () => {
    const entrada: EntradaFormulario = { form, mode, isAdmin, userBranchId, enabledBranchIds, prices, packagings, variantRows, hasVariantsModule }
    const clientErrors = validarProducto(entrada)
    if (Object.keys(clientErrors).length > 0) { setErrors(clientErrors); toast.error('Revisa los campos marcados.'); return }
    setSubmitting(true)
    try {
      if (mode === 'create') {
        const creado = await productsApi.create(armarPayloadAlta(entrada))
        toast.success('Producto creado.')
        onDone(creado)
      } else if (loaded) {
        const plan = armarPayloadEdicion({ ...entrada, loaded, variantId, precioATodas })
        // Primero el producto: si revienta (409 por SKU), la talla queda intacta.
        let actualizado = await productsApi.update(loaded.id, plan.productPatch)
        if (plan.variantPatch) actualizado = await productsApi.updateVariant(plan.variantPatch.variantId, plan.variantPatch.patch)
        toast.success('Producto actualizado.')
        onDone(actualizado)
      }
    } catch (err: unknown) {
      const r = erroresDeApi(err, variantRows, mode)
      setErrors((prev) => ({ ...prev, ...r.errors }))
      toast.error(r.mensaje)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Spinner size="lg" /></div>

  // Estos campos son los de la PRIMERA talla, no los del producto entero.
  const principalCargada = mode === 'edit' && hasVariantsModule && loaded && (loaded.variants?.length ?? 0) > 1 ? loaded.variants![0] : null
  const filaTalla = principalCargada && loaded && !esFilaPrincipal(loaded, variantId)
    ? loaded.variants!.find((v) => v.id === variantId) ?? null : null
  const cta = mode === 'create' ? 'Crear producto' : 'Guardar cambios'
  // Modo básico: con una sola sucursal la matriz sobra (ya va marcada); tallas
  // y empaques se esconden salvo que el producto ya los tenga (nada se apaga).
  const matrizOculta = modoBasico && branches.length === 1
  const muestraTallas = hasVariantsModule && campoVisible(campos, 'variants', (loaded?.variants?.length ?? 0) > 1 ? 'si' : null)

  const contenido = (
    <div className="p-0 sm:p-4 space-y-6">
      {principalCargada && (
        <>
          <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
            {filaTalla
              ? `SKU y código de aquí son los de la talla ${variantLabel(filaTalla, loaded?.name ?? '')}; el precio, el costo y los escalones son del producto (talla principal ${variantLabel(principalCargada, loaded?.name ?? '')}).`
              : `Nombre, precio y código de aquí son los de la talla ${variantLabel(principalCargada, loaded?.name ?? '')}. Las demás tallas, abajo.`}
          </p>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={precioATodas} onChange={(e) => setPrecioATodas(e.target.checked)} />
            Aplicar el precio a todas las tallas
          </label>
        </>
      )}
      <ProductBasicsSection value={form} onChange={setField} errors={errors} onSuggestSku={sugerirSku} suggestingSku={sugiriendoSku} campos={campos} />
      {mode === 'edit' && loaded && campoVisible(campos, 'image_url', loaded.image_url) && (
        <ProductImageUploader product={loaded} onUpdated={(p) => { setLoaded(p); setField('image_url', p.image_url ?? '') }} />
      )}
      <ProductCommercialSection value={form} onChange={setField} errors={errors} departments={departments} brands={brands} campos={campos} />
      <ProductTieredPricesSection prices={prices} onChange={setPrices} errors={errors}
        titulo={modoBasico ? 'Precio por cantidad' : undefined}
        help={modoBasico
          ? 'Ej.: «Mayoreo» a partir de 6 piezas, a $45 cada una.'
          : 'Para precios por cantidad (mayoreo, promo). Se aplica sobre el precio base.'} />
      {campoVisible(campos, 'packaging_units', packagings.length > 0 ? 'si' : null) && (
        <ProductPackagingSection packagings={packagings} onChange={setPackagings} errors={errors} />
      )}
      {mode === 'create' && muestraTallas && (
        <ProductVariantsSection baseSku={form.sku} rows={variantRows} onRowsChange={setVariantRows} firstIsPrincipal
          errors={errors} showInitialStock principalStock={form.initial_stock}
          onPrincipalStockChange={(v) => setField('initial_stock', v)} stockBranchName={sucursalStock?.name ?? null} />
      )}
      {mode === 'create' && isAdmin && !matrizOculta && (
        <ProductBranchMatrixSection branches={branches} activation={branchActivation} onToggle={toggleBranch} onSetAll={setAllBranches} errors={errors} />
      )}
      {mode === 'create' && (
        <ProductInitialStockSection value={form} onChange={setField} errors={errors} branches={branches} enabledBranchIds={enabledBranchIds}
          lockedBranchId={!isAdmin && userBranchId ? userBranchId : matrizOculta ? branches[0].id : undefined}
          perVariantTotal={hasVariantsModule && variantRows.length > 0 ? total : null}
          footer={isAdmin
            ? (matrizOculta ? 'La existencia se aplica a tu tienda.' : 'Para existencia en varias sucursales, usa Inventario después de crear.')
            : 'La existencia se aplica a tu sucursal.'} />
      )}
      {mode === 'edit' && muestraTallas && loaded && <ProductVariantsEditor product={loaded} onChanged={alCambiarTallas} />}
      <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center sm:justify-end gap-2 pt-2 border-t border-slate-800/60">
        <button type="button" className="dax-btn-secondary text-xs min-h-[44px] sm:min-h-0 justify-center" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="button" className="dax-btn-primary text-xs inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0"
          onClick={handleSubmit} disabled={submitting}>
          {submitting ? <Spinner size="sm" /> : <i className="fa-solid fa-save" />}
          {cta}
        </button>
      </div>
    </div>
  )

  if (presentacion === 'modal') return contenido
  const title = mode === 'create' ? 'Nuevo producto' : 'Editar producto'
  const iconCls = mode === 'create' ? 'fa-solid fa-plus' : 'fa-solid fa-pen-to-square'
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 flex-wrap">
        <i className={`${iconCls} text-indigo-400 text-xl`} />
        <h1 className="text-xl sm:text-2xl font-black text-white">{title}</h1>
        {!isAdmin && user?.branch_name && <span className="text-xs text-slate-500">· sucursal {user.branch_name}</span>}
      </div>
      <DaxCard>{contenido}</DaxCard>
    </div>
  )
}
