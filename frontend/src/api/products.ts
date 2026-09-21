import client from './client'
import type {
  Product,
  Brand,
  Department,
  ProductBranchStatus,
  CatalogKpis,
  UploadPreviewResponse,
} from '../types/products'
import type { AdjustmentCreate, KardexMovement } from './inventory'
import type { ExtraVariantPayload } from '../components/products/variantMatrix'

interface ProductsResponse {
  items: Product[]
  total: number
  page: number
  pages: number
}

interface ProductPricePayload {
  price_name: string
  min_quantity: number
  unit_price: number
  linked_package_id?: string | null
}

interface PackagingUnitPayload {
  name?: string
  barcode?: string | null
  units_per_package: number
  package_price: number
}

interface ProductCreate {
  sku: string
  name: string
  cost: number
  price: number
  brand_id?: string | null       // UUID
  department_id?: string | null  // UUID
  unit?: string                  // "unit" field (not unit_of_measure)
  image_url?: string | null
  description?: string | null
  barcode?: string | null
  // Color/talla de la VARIANTE PRINCIPAL (matriz boutique): su primera
  // combinación no va en `extra_variants`, va aquí. Sin ellos la principal
  // sigue naciendo como "Estándar" (resto de los tenants).
  color?: string
  size?: string
  // Ficha boutique: el género se valida en el backend (HOMBRE|MUJER|UNISEX|NINO);
  // el modelo entra en el nombre de venta y el material es informativo.
  gender?: string | null
  model?: string | null
  material?: string | null
  // Admin-only extensions — all optional to keep existing callers working
  has_iva?: boolean
  tax_rate?: number
  initial_stock?: number
  branch_id?: number | null
  target_branch_ids?: number[] | null
  uses_inventory?: boolean
  prices?: ProductPricePayload[]
  packaging_units?: PackagingUnitPayload[]
  extra_variants?: ExtraVariantPayload[]
}

/**
 * Campos del `ProductBranchStatus` que CAJERO/GERENTE pueden editar para su
 * sucursal. Todos opcionales — solo manda los que cambias.
 *
 * `price_override: null` borra el override (hereda el precio base del producto).
 * `branchId` query param solo aplica para ADMIN/DUEÑO; CAJERO/GERENTE lo ignoran
 * — el backend deriva la sucursal del JWT (defense in depth).
 */
export interface BranchStatusPatch {
  price_override?: number | null
  min_stock_alert?: number | null
  max_stock_limit?: number | null
  is_active_pos?: boolean
  is_active_hq?: boolean
  is_visible?: boolean
}

type UploadResult = { created: number; updated: number; failed: number; errors: string[] }

// Overloads — preserve legacy 1/2/3-arg shape, opt-in to preview via 4th arg.
function uploadProductsImpl(
  file: File,
  scope?: 'branch' | 'all' | 'selected',
  targetBranchIds?: string,
): Promise<UploadResult>
function uploadProductsImpl(
  file: File,
  scope: 'branch' | 'all' | 'selected',
  targetBranchIds: string | undefined,
  options: { dryRun: true },
): Promise<UploadPreviewResponse>
function uploadProductsImpl(
  file: File,
  scope: 'branch' | 'all' | 'selected',
  targetBranchIds: string | undefined,
  options: { dryRun?: false },
): Promise<UploadResult>
async function uploadProductsImpl(
  file: File,
  scope: 'branch' | 'all' | 'selected' = 'branch',
  targetBranchIds?: string,
  options: { dryRun?: boolean } = {},
): Promise<UploadResult | UploadPreviewResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('scope', scope)
  if (targetBranchIds) form.append('target_branch_ids', targetBranchIds)
  if (options.dryRun) form.append('dry_run', 'true')
  const { data } = await client.post('/products/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  if (options.dryRun) {
    return data as UploadPreviewResponse
  }
  return {
    created: data.created ?? 0,
    updated: data.updated ?? 0,
    failed: data.failed ?? 0,
    errors: data.errors ?? [],
  }
}

export const productsApi = {
  search: async (q: string, skip = 0, limit = 50): Promise<ProductsResponse> => {
    const { data } = await client.get<ProductsResponse>('/products/', {
      params: { search: q, skip, limit },
    })
    if (Array.isArray(data)) {
      return { items: data, total: data.length, page: 0, pages: 1 }
    }
    return { items: data.items ?? [], total: data.total ?? 0, page: data.page ?? 0, pages: data.pages ?? 1 }
  },

  /**
   * Búsqueda por código ESCANEADO — coincidencia exacta.
   *
   * `posSearch` busca con `%parcial%`, correcto cuando la cajera teclea. Un
   * escaneo trae el código completo, y con parcial también devuelve los
   * productos cuyo código lo CONTIENE: en el pasillo del scanner de tienda
   * eso es editarle el precio al producto equivocado. Por eso `exact: true`.
   *
   * `branchId` es la sucursal donde está parado el admin — el backend solo
   * respeta el hint para ADMINISTRADOR/DUEÑO; el scope real (org + sucursal)
   * lo sigue aplicando el mismo helper de visibilidad que usa el resto del
   * catálogo.
   */
  scanExact: async (code: string, branchId?: number | null): Promise<Product[]> => {
    const q = (code ?? '').trim()
    if (!q) return []
    const { data } = await client.get<Product[]>('/products/pos/search', {
      params: { q, exact: true, ...(branchId ? { branch_id: branchId } : {}) },
    })
    return Array.isArray(data) ? data : []
  },

  /**
   * POST /api/inventory/adjust — registra el conteo del scanner de tienda
   * como un movimiento de inventario (delta con signo, ya traducido por
   * `stockAdjust.ts`). Pasa por el mismo endpoint que `inventoryApi.createAdjustment`
   * para que el movimiento quede firmado en el kardex con quién y cuándo.
   */
  adjustStock: async (payload: AdjustmentCreate): Promise<KardexMovement> => {
    const { data } = await client.post<KardexMovement>('/inventory/adjust', payload)
    return data
  },

  /**
   * GET /api/products/ — listado paginado/filtrado.
   *
   * NOTE (defense in depth): aunque `params` permite enviar `branch_id` y
   * `active_in_branch`, el backend IGNORA estos hints para roles no-admin
   * (CAJERO/GERENTE) y fuerza los valores desde `current_user.branch_id`
   * derivado del JWT. Solo ADMINISTRADOR/DUEÑO pueden influir sobre el
   * filtrado por sucursal (selector HQ). Los callers no-admin no deben
   * enviarlos — el backend los va a descartar igualmente.
   */
  list: async (params?: Record<string, unknown>): Promise<ProductsResponse> => {
    // Normaliza nombres de params para que coincidan con el backend
    const normalized: Record<string, unknown> = { ...params }
    if ('q' in normalized) { normalized.search = normalized.q; delete normalized.q }
    if ('is_active' in normalized) { normalized.active_only = normalized.is_active; delete normalized.is_active }
    const { data } = await client.get<ProductsResponse>('/products/', { params: normalized })
    // Manejo defensivo: si el backend devuelve un array plano en vez de {items, total}
    if (Array.isArray(data)) {
      return { items: data, total: data.length, page: 0, pages: 1 }
    }
    return data
  },

  /**
   * GET /api/products/sku-suggest — SKU que propone la convención
   * MARCA-PRENDA-MODELO-COLOR-TALLA.
   *
   * Es una SUGERENCIA: nunca se aplica sola, el alta sigue aceptando cualquier
   * SKU único. `available` dice si el código ya lo ocupa otra variante de la
   * organización (el mismo SKU en otra tienda no estorba).
   */
  skuSuggest: async (args: {
    name: string
    brand?: string | null
    model?: string | null
    color?: string | null
    size?: string | null
  }): Promise<{ sku: string; available: boolean }> => {
    const params: Record<string, string> = { name: args.name ?? '' }
    for (const k of ['brand', 'model', 'color', 'size'] as const) {
      const v = (args[k] ?? '').trim()
      if (v) params[k] = v
    }
    const { data } = await client.get<{ sku: string; available: boolean }>(
      '/products/sku-suggest', { params },
    )
    return data
  },

  getById: async (id: string): Promise<Product> => {
    const { data } = await client.get<Product>(`/products/${id}`)
    return data
  },

  /**
   * GET /api/products/stats/catalog-kpis — KPIs contextuales.
   * Respeta los mismos filtros que `list()`. Admin-only para drill-down
   * por sucursal; el scope para no-admins siempre es su propia rama.
   */
  catalogKpis: async (params?: {
    search?: string
    department_id?: string
    brand_id?: string
    approval_status?: string
    branch_id?: number
  }): Promise<{
    total_skus: number
    active_pos: number
    pending_approval: number
    no_branch: number
    critical_stock: number
    zero_stock: number
    threshold: number
  }> => {
    const { data } = await client.get('/products/stats/catalog-kpis', { params })
    return data
  },

  create: async (payload: ProductCreate): Promise<Product> => {
    const { data } = await client.post<Product>('/products/', payload)
    return data
  },

  update: async (id: string, payload: Partial<ProductCreate>): Promise<Product> => {
    const { data } = await client.put<Product>(`/products/${id}`, payload)
    return data
  },

  updateStatus: async (id: string, is_active: boolean): Promise<Product> => {
    const { data } = await client.put<Product>(`/products/${id}`, { is_active })
    return data
  },

  /**
   * POST /api/products/{id}/restore — revierte un soft-delete (admin-only).
   * El admin debe re-activar PBS desde la matriz para que el producto vuelva a vender.
   */
  restore: async (id: string): Promise<{ status: string; product_id: string; message: string }> => {
    const { data } = await client.post(`/products/${id}/restore`)
    return data
  },

  /** POST /api/products/{id}/variants — agrega variantes de color/talla (módulo `variants`). */
  createVariants: async (productId: string, variants: ExtraVariantPayload[]): Promise<Product> => {
    const { data } = await client.post<Product>(`/products/${productId}/variants`, { variants })
    return data
  },

  updateVariant: async (
    variantId: string,
    patch: { color?: string | null; size?: string | null; sku?: string; barcode?: string | null; price?: number; cost?: number },
  ): Promise<Product> => {
    const { data } = await client.put<Product>(`/products/variants/${variantId}`, patch)
    return data
  },

  deleteVariant: async (variantId: string): Promise<void> => {
    await client.delete(`/products/variants/${variantId}`)
  },

  /**
   * PATCH /api/products/variants/{variant_id}/branch-status
   *
   * Actualiza campos del `ProductBranchStatus` para la sucursal del CAJERO/GERENTE.
   * ADMIN/DUEÑO deben pasar `branchId` para especificar la sucursal target.
   * Para roles no-admin el backend ignora `branchId` y usa `current_user.branch_id`.
   *
   * Errores esperados:
   * - 403: CAJERO/GERENTE intentando editar una sucursal distinta a la suya.
   * - 404: variant no visible para el usuario (no pertenece a su org / sucursal).
   */
  updateBranchStatus: async (
    variantId: string,
    body: BranchStatusPatch,
    branchId?: number,
  ): Promise<ProductBranchStatus> => {
    const params = branchId != null ? { branch_id: branchId } : undefined
    const { data } = await client.patch<ProductBranchStatus>(
      `/products/variants/${variantId}/branch-status`,
      body,
      { params },
    )
    return data
  },

  /** GET /api/products/{id}/branch-status — todas las filas PBS para el product. */
  getBranchStatuses: async (productId: string): Promise<ProductBranchStatus[]> => {
    const { data } = await client.get<ProductBranchStatus[]>(
      `/products/${productId}/branch-status`,
    )
    return Array.isArray(data) ? data : []
  },

  /**
   * GET /api/products/{id}/audit-log — timeline PBS del producto (admin-only).
   */
  getAuditLog: async (productId: string, limit = 50): Promise<{
    items: Array<{
      id: number
      action: string
      entity_type: string
      entity_id: string
      actor_username: string | null
      actor_user_id: number | null
      created_at: string | null
      payload: Record<string, unknown>
    }>
  }> => {
    const { data } = await client.get(`/products/${productId}/audit-log`, { params: { limit } })
    return data
  },

  /**
   * POST /api/products/branch-status/bulk-toggle — habilita o deshabilita
   * `is_active_pos` para N variantes en M sucursales (admin-only).
   */
  bulkToggleBranchStatus: async (payload: {
    variant_ids: string[]
    branch_ids: number[]
    is_active_pos: boolean
  }): Promise<{ message: string; updated_records: number }> => {
    const { data } = await client.post('/products/branch-status/bulk-toggle', payload)
    return data
  },

  /**
   * PUT /api/products/{id}/approve — marca APPROVED (admin-only).
   */
  approve: async (id: string): Promise<{ status: string; product_id: string }> => {
    const { data } = await client.put(`/products/${id}/approve`)
    return data
  },

  /**
   * PUT /api/products/{id}/reject — marca REJECTED y desactiva PBS en
   * todas las sucursales (admin-only).
   */
  reject: async (id: string): Promise<{ status: string; product_id: string }> => {
    const { data } = await client.put(`/products/${id}/reject`)
    return data
  },

  /**
   * POST /api/products/{id}/duplicate — clona con SKU "-COPY-N"
   * (admin-only). No copia stock.
   */
  duplicate: async (id: string): Promise<Product> => {
    const { data } = await client.post<Product>(`/products/${id}/duplicate`)
    return data
  },

  /**
   * POST /api/products/branch-status/clone — replica PBS de una sucursal
   * origen a N sucursales destino (admin-only).
   */
  cloneBranchStatus: async (payload: {
    from_branch_id: number
    to_branch_ids: number[]
    variant_ids?: string[]
    overwrite?: boolean
  }): Promise<{
    created: number
    updated: number
    skipped: number
    from_branch_id: number
    to_branch_ids: number[]
  }> => {
    const { data } = await client.post('/products/branch-status/clone', payload)
    return data
  },

  /** POST /api/products/{id}/image — upload image file (JPEG/PNG/WEBP, ≤2 MB). */
  uploadImage: async (id: string, file: File): Promise<Product> => {
    const form = new FormData()
    form.append('file', file)
    const { data } = await client.post<Product>(`/products/${id}/image`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  /** DELETE /api/products/{id}/image — remove image file and clear image_url. */
  deleteImage: async (id: string): Promise<Product> => {
    const { data } = await client.delete<Product>(`/products/${id}/image`)
    return data
  },

  getBrands: async (): Promise<Brand[]> => {
    const { data } = await client.get<Brand[]>('/brands/')
    return Array.isArray(data) ? data : (data as any)?.items ?? []
  },

  createBrand: async (payload: { name: string; logo_url?: string }): Promise<Brand> => {
    const { data } = await client.post<Brand>('/brands/', payload)
    return data
  },

  updateBrand: async (id: string, payload: { name?: string; logo_url?: string }): Promise<Brand> => {
    const { data } = await client.put<Brand>(`/brands/${id}/`, payload)
    return data
  },

  deleteBrand: async (id: string): Promise<void> => {
    await client.delete(`/brands/${id}/`)
  },

  getDepartments: async (): Promise<Department[]> => {
    const { data } = await client.get<Department[]>('/departments/')
    return Array.isArray(data) ? data : (data as any)?.items ?? []
  },

  createDepartment: async (payload: { name: string }): Promise<Department> => {
    const { data } = await client.post<Department>('/departments/', payload)
    return data
  },

  updateDepartment: async (id: string, payload: { name?: string }): Promise<Department> => {
    const { data } = await client.put<Department>(`/departments/${id}/`, payload)
    return data
  },

  deleteDepartment: async (id: string): Promise<void> => {
    await client.delete(`/departments/${id}/`)
  },

  posSearch: async (
    q: string,
    order_by: 'best_sellers' | 'name_asc' | 'price_asc' | 'price_desc' = 'best_sellers',
  ): Promise<Product[]> => {
    const { data } = await client.get<Product[]>('/products/pos/search', { params: { q, order_by } })
    return Array.isArray(data) ? data : (data as any)?.items ?? []
  },

  /**
   * GET /api/products/export/excel — descarga Excel con productos visibles.
   * Sin params → catálogo completo (o rama del usuario, según rol).
   * Con params → respeta los mismos filtros que `list()`: search, department_id,
   * brand_id, approval_status, branch_id, include_inactive.
   */
  downloadTemplate: async (params?: {
    search?: string
    department_id?: string
    brand_id?: string
    approval_status?: string
    branch_id?: number
    include_inactive?: boolean
  }): Promise<void> => {
    const res = await client.get('/products/export/excel', { params, responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    const ts = new Date().toISOString().slice(0, 10)
    a.download = `catalogo_${ts}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  },

  /**
   * GET /api/products/barcodes/missing-count — cuántas tallas visibles
   * siguen sin código de barras (el botón "Generar códigos" se apoya en esto).
   */
  barcodesMissingCount: async (): Promise<number> => {
    const { data } = await client.get<{ missing: number }>('/products/barcodes/missing-count')
    return Number(data?.missing ?? 0)
  },

  /**
   * POST /api/products/barcodes/assign-missing — genera el código interno de
   * las variantes que no tienen. Solo ADMINISTRADOR/DUEÑO. Nunca sobrescribe
   * un código existente. Sin `productId` recorre todo el catálogo.
   */
  assignMissingBarcodes: async (productId?: string): Promise<number> => {
    const { data } = await client.post<{ assigned: number }>(
      '/products/barcodes/assign-missing',
      productId ? { product_id: productId } : {},
    )
    return Number(data?.assigned ?? 0)
  },

  /**
   * GET /api/products/export/labels.csv — CSV de etiquetas (una fila por
   * talla) para ZebraDesigner / la app de la etiquetadora.
   */
  downloadLabelsCsv: async (productId?: string): Promise<void> => {
    const res = await client.get('/products/export/labels.csv', {
      params: productId ? { product_id: productId } : undefined,
      responseType: 'blob',
    })
    const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    const ts = new Date().toISOString().slice(0, 10)
    a.download = `etiquetas_${ts}.csv`
    a.click()
    URL.revokeObjectURL(url)
  },

  /**
   * POST /api/products/upload — importación masiva desde Excel/CSV.
   *
   * NOTE (defense in depth): `scope` y `targetBranchIds` son hints. Backend
   * valida rol y fuerza `scope='branch'` + target = `current_user.branch_id`
   * para CAJERO/GERENTE, ignorando cualquier otra elección. Solo admins
   * (ADMINISTRADOR/DUEÑO) pueden elegir `'all'` o `'selected'` con IDs
   * arbitrarios.
   */
  uploadProducts: uploadProductsImpl,

  getCatalogKpis: async (): Promise<CatalogKpis> => {
    const { data } = await client.get<CatalogKpis>('/products/stats/catalog-kpis')
    return data ?? { total_skus: 0, active_pos: 0, pending_approval: 0, no_branch: 0, critical_stock: 0, zero_stock: 0 }
  },
}
