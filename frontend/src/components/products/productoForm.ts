/**
 * Lógica pura del formulario de producto: la única validación y el único
 * armado de payload para alta y edición. `FormularioProducto.tsx` solo pinta.
 *
 * Sale de fusionar lo que tenían copiado la antigua página de alta, ProductForm,
 * ProductModal (HQ) y ProductFormModal (sucursal). Reglas que el backend
 * exige y aquí se repiten para avisar antes de mandar: precio > 0, SKU
 * requerido, escalones y empaques bien formados.
 */
import type { ProductCreate, ProductUpdate } from '../../api/products'
import type { Product } from '../../types/products'
import { fieldErrorsFromDetail, summarizeFieldErrors } from '../../utils/apiErrors'
import { esFilaPrincipal, planIdentidadDeFila } from '../branch/variantEdit'
import type { PackagingRow, PriceRow, ProductErrors, ProductFormValue } from './types'
import { splitPrincipal, toExtraVariants, variantDetailErrors, variantFieldErrors, type VariantRow } from './variantMatrix'

export interface EntradaFormulario {
  form: ProductFormValue
  mode: 'create' | 'edit'
  isAdmin: boolean
  userBranchId: number | null
  /** Admin: sucursales marcadas en la matriz. Cajero/gerente: la suya. */
  enabledBranchIds: number[]
  prices: PriceRow[]
  packagings: PackagingRow[]
  variantRows: VariantRow[]
  hasVariantsModule: boolean
}

/** Existencia que traen las tallas hermanas de la matriz (sin la principal). */
export function stockHermanas(variantRows: VariantRow[], hasVariantsModule: boolean): number {
  return splitPrincipal(hasVariantsModule ? variantRows : []).extras
    .reduce((acc, r) => acc + (Number(r.initial_stock) || 0), 0)
}

/** Existencia inicial total del alta: principal + hermanas. */
export function totalInicial(form: ProductFormValue, variantRows: VariantRow[], hasVariantsModule: boolean): number {
  return (Number(form.initial_stock || '0') || 0) + stockHermanas(variantRows, hasVariantsModule)
}

export function validarProducto(e: EntradaFormulario): ProductErrors {
  const { form, mode, isAdmin, userBranchId, enabledBranchIds, prices, packagings, variantRows, hasVariantsModule } = e
  const errores: ProductErrors = {}
  if (!form.name.trim()) errores.name = 'Requerido'
  if (!form.sku.trim()) errores.sku = 'Requerido'
  const precio = Number(form.price)
  const costo = Number(form.cost)
  // El backend rechaza precio 0 (`validar_precio`); avisar aquí evita un 422 opaco.
  if (!Number.isFinite(precio) || precio <= 0) errores.price = 'Precio mayor a 0'
  if (!Number.isFinite(costo) || costo < 0) errores.cost = 'Número ≥ 0'
  if (mode === 'create') {
    const stock = Number(form.initial_stock || '0')
    if (!Number.isFinite(stock) || stock < 0) errores.initial_stock = 'Número ≥ 0'
    const total = totalInicial(form, variantRows, hasVariantsModule)
    if (isAdmin) {
      if (enabledBranchIds.length === 0) errores.target_branch_ids = 'Activa al menos una sucursal'
      // La existencia se reparte por talla: la sucursal hace falta si
      // cualquiera de las filas trae existencia, no solo la principal.
      if (total > 0 && !form.initial_stock_branch_id) errores.initial_stock_branch_id = 'Requerido con existencia inicial'
    } else if (!userBranchId) {
      errores.target_branch_ids = 'Tu usuario no tiene sucursal asignada'
    }
  }
  prices.forEach((p, i) => {
    if (!p.price_name.trim()) errores[`prices.${i}.price_name`] = 'Requerido'
    if (!Number.isFinite(Number(p.min_quantity)) || Number(p.min_quantity) <= 0)
      errores[`prices.${i}.min_quantity`] = 'Cantidad mínima mayor a 0'
    if (!Number.isFinite(Number(p.unit_price)) || Number(p.unit_price) < 0)
      errores[`prices.${i}.unit_price`] = 'Número ≥ 0'
  })
  packagings.forEach((u, i) => {
    if (!u.name.trim()) errores[`packaging.${i}.name`] = 'Requerido'
    if (!Number.isFinite(Number(u.units_per_package)) || Number(u.units_per_package) <= 0)
      errores[`packaging.${i}.units_per_package`] = 'Unidades mayores a 0'
    if (!Number.isFinite(Number(u.package_price)) || Number(u.package_price) < 0)
      errores[`packaging.${i}.package_price`] = 'Número ≥ 0'
  })
  if (form.has_iva && !Number.isFinite(Number(form.tax_rate))) errores.tax_rate = 'Escribe un número'
  if (mode === 'create' && hasVariantsModule) {
    // La primera fila es la principal: su SKU es el base, no se valida aparte.
    const skus = new Set<string>([form.sku.trim().toLowerCase()])
    splitPrincipal(variantRows).extras.forEach((r, i) => {
      const s = r.sku.trim().toLowerCase()
      if (!s) errores[`variants.${i}.sku`] = 'SKU requerido'
      else if (skus.has(s)) errores[`variants.${i}.sku`] = 'SKU repetido'
      skus.add(s)
      if (r.price.trim() && !(Number(r.price) > 0)) errores[`variants.${i}.price`] = 'Precio mayor a 0'
      const st = Number(r.initial_stock)
      if (r.initial_stock.trim() && !(Number.isFinite(st) && st >= 0)) errores[`variants.${i}.initial_stock`] = 'Número ≥ 0'
    })
  }
  return errores
}

const escalones = (prices: PriceRow[]) => prices.map((p) => ({
  price_name: p.price_name, min_quantity: Number(p.min_quantity), unit_price: Number(p.unit_price),
}))

const empaques = (packagings: PackagingRow[]) => packagings.map((u) => ({
  name: u.name.trim() || 'Caja', barcode: u.barcode.trim() || null,
  units_per_package: Number(u.units_per_package), package_price: Number(u.package_price),
}))

/** Campos comunes a alta y edición, ya limpios. */
function camposComunes(form: ProductFormValue) {
  return {
    name: form.name.trim(),
    unit: form.unit,
    description: form.description.trim() || null,
    image_url: form.image_url.trim() || null,
    department_id: form.department_id || null,
    brand_id: form.brand_id || null,
    gender: form.gender || null,
    model: form.model.trim() || null,
    material: form.material.trim() || null,
    price: Number(form.price),
    cost: Number(form.cost),
    has_iva: form.has_iva,
    tax_rate: form.has_iva ? Number(form.tax_rate) : 0,
  }
}

export function armarPayloadAlta(e: EntradaFormulario): ProductCreate {
  const { form, isAdmin, userBranchId, enabledBranchIds, prices, packagings, variantRows, hasVariantsModule } = e
  // Matriz boutique: la primera combinación ES la variante principal
  // (`color`/`size` del producto); el resto viajan como `extra_variants`.
  const { principal, extras } = splitPrincipal(hasVariantsModule ? variantRows : [])
  const variantes = principal
    ? {
        ...(principal.color ? { color: principal.color } : {}),
        ...(principal.size ? { size: principal.size } : {}),
        ...(extras.length > 0 ? { extra_variants: toExtraVariants(extras) } : {}),
      }
    : {}
  const total = totalInicial(form, variantRows, hasVariantsModule)
  // La sucursal destino viaja si CUALQUIER talla trae existencia: sin ella el
  // backend no sabría dónde meter la de las hermanas.
  const sucursalStock = total > 0 ? (isAdmin ? Number(form.initial_stock_branch_id) : userBranchId) : null
  return {
    ...camposComunes(form),
    sku: form.sku.trim(),
    barcode: form.barcode.trim() || null,
    initial_stock: Number(form.initial_stock || '0') || 0,
    branch_id: sucursalStock,
    // Solo el admin reparte sucursales; el backend ignora el campo a los demás.
    ...(isAdmin ? { target_branch_ids: enabledBranchIds } : {}),
    prices: escalones(prices),
    packaging_units: empaques(packagings),
    ...variantes,
  }
}

export interface EntradaEdicion extends EntradaFormulario {
  loaded: Product
  /** Talla de la que salió el renglón (lista de sucursal); sin ella se edita la principal. */
  variantId?: string
  precioATodas: boolean
}

export interface PlanEdicion {
  productPatch: ProductUpdate
  variantPatch: { variantId: string; patch: { sku?: string; barcode?: string | null } } | null
}

export function armarPayloadEdicion(e: EntradaEdicion): PlanEdicion {
  const { form, prices, packagings, loaded, variantId, precioATodas } = e
  // El SKU/código de una talla no principal NO puede viajar en PUT /products/{id}:
  // ahí sobrescribiría los de la principal (ver components/branch/variantEdit.ts).
  const identidad = planIdentidadDeFila(loaded, variantId, { sku: form.sku.trim(), barcode: form.barcode.trim() || null })
  const varias = (loaded.variants?.length ?? 0) > 1
  return {
    productPatch: {
      ...camposComunes(form),
      ...identidad.productPatch,
      // Solo tiene sentido con varias tallas; sin ellas no se manda.
      ...(varias ? { precio_a_todas_las_tallas: precioATodas } : {}),
      // Cargados desde GET /products/{id}: mandarlos completos conserva lo que había.
      prices: escalones(prices),
      packaging_units: empaques(packagings),
    },
    variantPatch: identidad.variantPatch,
  }
}

export interface EstadoDesdeProducto { form: ProductFormValue; prices: PriceRow[]; packagings: PackagingRow[] }

/** Estado del formulario a partir de un producto cargado con GET /products/{id}. */
export function formDesdeProducto(p: Product, variantId?: string): EstadoDesdeProducto {
  const principal = p.variants?.[0]
  const fila = variantId && !esFilaPrincipal(p, variantId) ? p.variants?.find((v) => v.id === variantId) : undefined
  const identidad = fila ?? principal
  return {
    form: {
      name: p.name ?? '',
      sku: (identidad?.sku ?? p.sku ?? '') as string,
      barcode: (identidad?.barcode ?? p.barcode ?? '') as string,
      unit: p.unit ?? 'pza',
      description: p.description ?? '',
      image_url: p.image_url ?? '',
      department_id: (p.department?.id ?? '') as string,
      brand_id: (p.brand_id ?? '') as string,
      gender: p.gender ?? '',
      model: p.model ?? '',
      material: p.material ?? '',
      price: String(principal?.price ?? p.price ?? ''),
      cost: String(principal?.cost ?? p.cost ?? ''),
      has_iva: Boolean(principal?.has_iva ?? p.has_iva ?? false),
      tax_rate: String(principal?.tax_rate ?? p.tax_rate ?? '16'),
      initial_stock: '0',
      initial_stock_branch_id: '',
    },
    // Escalones: variante principal o top-level como respaldo.
    prices: (principal?.prices ?? p.prices ?? []).map((tp) => ({
      id: tp.id, price_name: tp.price_name, min_quantity: Number(tp.min_quantity), unit_price: Number(tp.unit_price),
    })),
    packagings: (p.packaging_units ?? []).map((u) => ({
      id: u.id, name: u.name, barcode: u.barcode ?? '', units_per_package: Number(u.units_per_package), package_price: Number(u.package_price),
    })),
  }
}

const CAMPOS_IDENTIDAD = ['sku', 'barcode', 'price', 'cost', 'has_iva', 'tax_rate'] as const

/**
 * ¿Cambió la identidad del formulario tras editar tallas? Sí si la principal ya
 * no es la misma, si `variantId` dejó de existir, o si la talla de identidad
 * (la de `variantId` si sigue viva; si no, la principal) o la principal (de ahí
 * salen precio y costo) cambió en línea de sku, código, precio, costo o IVA.
 */
export function principalCambio(antes: Product | null, despues: Product, variantId?: string): boolean {
  if (antes?.variants?.[0]?.id !== despues.variants?.[0]?.id) return true
  const vivas = despues.variants ?? []
  if (variantId && !vivas.some((v) => v.id === variantId)) return true
  const viejas = antes?.variants ?? []
  const distinta = (id: string | undefined) => {
    const v0 = viejas.find((v) => v.id === id) as Record<string, unknown> | undefined
    const v1 = vivas.find((v) => v.id === id) as Record<string, unknown> | undefined
    if (!v0 || !v1) return false
    return CAMPOS_IDENTIDAD.some((c) => (v0[c] ?? null) !== (v1[c] ?? null))
  }
  return distinta(vivas[0]?.id) || distinta(variantId)
}

export interface ErroresDeApi { errors: ProductErrors; mensaje: string }

/** Traduce la respuesta de error de la API a errores por campo y un aviso. */
export function erroresDeApi(err: unknown, variantRows: VariantRow[], mode: 'create' | 'edit'): ErroresDeApi {
  const e = err as { response?: { status?: number; data?: { detail?: unknown } } } | null
  const status = e?.response?.status
  const detail = e?.response?.data?.detail
  // Un 409 de la matriz (SKU o código repetido de una talla) cita la fila
  // culpable: marcarla ahí en vez de acusar al SKU base del producto.
  const porFila = variantDetailErrors(detail as string | undefined, splitPrincipal(variantRows).extras)
  if (Object.keys(porFila).length > 0) return { errors: porFila, mensaje: 'Revisa la variante marcada.' }
  const errors: ProductErrors = {}
  if (status === 409 || (typeof detail === 'string' && detail.toLowerCase().includes('sku'))) {
    errors.sku = typeof detail === 'string' ? detail : 'SKU duplicado'
  }
  // Un 422 trae `detail` como LISTA de campos.
  const porCampo = variantFieldErrors(fieldErrorsFromDetail(detail))
  if (Object.keys(porCampo).length > 0) return { errors: { ...errors, ...porCampo }, mensaje: summarizeFieldErrors(porCampo) }
  const generico = `No se pudo ${mode === 'create' ? 'crear' : 'actualizar'} el producto.`
  return { errors, mensaje: typeof detail === 'string' ? detail : generico }
}
