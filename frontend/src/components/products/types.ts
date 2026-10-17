import type { Brand, Department } from '../../types/products'
import type { Branch } from '../../types/auth'

/** Form state compartido entre AdminProductCreate y ProductForm (cajero). */
export interface ProductFormValue {
  name: string
  sku: string
  barcode: string
  unit: string
  description: string
  image_url: string
  department_id: string
  brand_id: string
  /** Ficha boutique: '' = sin capturar (no se manda o se manda null). */
  gender: string
  model: string
  material: string
  price: string
  cost: string
  has_iva: boolean
  tax_rate: string
  /** false = servicio o producto sin existencias (no descuenta inventario). */
  uses_inventory: boolean
  initial_stock: string
  initial_stock_branch_id: string
}

export interface BranchActivation {
  enabled: boolean
  is_active_pos: boolean
  is_active_hq: boolean
  is_visible: boolean
}

export const EMPTY_PRODUCT_FORM: ProductFormValue = {
  name: '',
  sku: '',
  barcode: '',
  unit: 'pza',
  description: '',
  image_url: '',
  department_id: '',
  brand_id: '',
  gender: '',
  model: '',
  material: '',
  price: '',
  cost: '',
  has_iva: false,
  tax_rate: '16',
  uses_inventory: true,
  initial_stock: '0',
  initial_stock_branch_id: '',
}

export type ProductErrors = Record<string, string>

export type SetField = <K extends keyof ProductFormValue>(key: K, value: ProductFormValue[K]) => void

/** Fila editable de precio escalonado (mayoreo, promoción, etc). */
export interface PriceRow {
  id?: string
  price_name: string
  min_quantity: number
  unit_price: number
}

export const emptyPriceRow = (): PriceRow => ({ price_name: '', min_quantity: 1, unit_price: 0 })

/** Fila editable de empaque (caja, master…). */
export interface PackagingRow {
  id?: string
  name: string
  barcode: string
  units_per_package: number
  package_price: number
}

export const emptyPackagingRow = (): PackagingRow => ({ name: 'Caja', barcode: '', units_per_package: 1, package_price: 0 })

export type { Brand, Department, Branch }
