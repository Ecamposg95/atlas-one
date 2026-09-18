export interface ProductPrice {
  id: string
  price_name: string
  min_quantity: number
  unit_price: number
  linked_package_id: string | null
}

export interface PackagingUnit {
  id: string
  name: string           // ej: "Caja", "Master"
  barcode: string | null
  units_per_package: number
  package_price: number
  weight?: number | null
  dimensions?: string | null
}

export interface StockLevel {
  branch_id: number
  branch_name?: string | null
  qty_on_hand: number
  is_active: boolean
  is_active_pos?: boolean | null
}

export interface ProductBranchStatus {
  id: string
  variant_id: string
  branch_id: number
  branch_name?: string | null
  is_active_pos: boolean
  is_active_hq: boolean
  is_visible: boolean
  price_override?: number | null
  min_stock_alert?: number | null
  max_stock_limit?: number | null
}

export interface ProductVariant {
  id: string
  product_id: string
  sku: string
  variant_name?: string | null   // "Rojo / M" o "Estándar"
  color?: string | null
  size?: string | null
  price: number
  /** Precio que el POS COBRA en la sucursal activa: el `price_override` de la
   *  sucursal si lo hay, y si no `price`. El editor de variantes sigue usando
   *  `price` (el base). Ausente en respuestas que no pasan por
   *  `_compute_product_read`: usar `effective_price ?? price`. */
  effective_price?: number | null
  cost: number
  barcode?: string | null
  has_iva?: boolean
  tax_rate?: number
  stock_total?: number | string  // Decimal del backend; usar Number()
  prices?: ProductPrice[]
  packaging_units?: PackagingUnit[]
}

export interface Product {
  id: string                       // UUID
  sku: string
  name: string
  description: string | null
  brand_id: string | null          // UUID
  brand_name: string | null
  department: { id: string; name: string } | null
  department_name: string | null
  unit: string | null              // "pza", "kg", etc.
  cost: number
  price: number
  stock: number
  stock_total?: number
  global_stock?: number            // Total across all branches
  min_stock?: number | null
  image_url: string | null
  is_active: boolean
  barcode?: string | null
  has_iva?: boolean
  tax_rate?: number
  uses_inventory?: boolean
  approval_status?: string | null

  // Precios escalonados de la variante principal
  prices?: ProductPrice[]

  // Empaques de la variante principal
  packaging_units?: PackagingUnit[]

  // Variantes completas (orden de creación)
  variants?: ProductVariant[]
  // Qué variante representan sku/price/stock_total: la que empató un escaneo o la primera
  matched_variant_id?: string | null

  // Stock por sucursal
  stock_levels?: StockLevel[]

  // Highlights de empaque principal
  main_packaging_name?: string | null
  main_packaging_price?: number | null
  main_packaging_units?: number | null

  // Estado por sucursal (habilitación comercial)
  branch_statuses?: ProductBranchStatus[]
}

export interface Brand {
  id: string                       // UUID
  name: string
  logo_url: string | null
  product_count?: number
}

export interface Department {
  id: string                       // UUID
  name: string
}

export interface CatalogKpis {
  total_skus: number
  active_pos: number
  pending_approval: number
  no_branch: number
  critical_stock: number
  zero_stock: number
}

export interface UploadRowPreview {
  action: 'NEW' | 'UPDATE' | 'ERROR'
  sku: string | null
  name: string | null
  price: number | null
  error_message: string | null
}

export interface UploadPreviewResponse {
  total_rows: number
  to_create: number
  to_update: number
  errors: number
  preview: UploadRowPreview[]
  error_details: string[]
}
