export type DocType = 'SALE' | 'QUOTE' | 'RETURN' | 'LAYAWAY'
export type DocStatus = 'OPEN' | 'CLOSED' | 'CANCELLED' | 'PARTIAL' | 'PAID' | 'REFUNDED_PARTIAL' | 'REFUNDED_TOTAL'

export interface SaleLineItem {
  id: string
  variant_id: string
  sku: string | null
  description: string | null
  quantity: number
  unit_price: number
  total_line: number
  has_iva?: boolean
  tax_rate?: number
}

export interface Payment {
  id: string
  method: string
  amount: number
  created_at?: string
}

export interface SalesDocument {
  id: string
  doc_type: DocType
  status: DocStatus
  branch_id: number
  branch_name?: string | null
  seller_id: number
  customer_id: number | null
  customer_name: string | null
  series: string | null
  folio: number | null
  subtotal: number
  tax_amount: number
  total_amount: number
  requires_invoice: boolean
  created_at: string
  lines: SaleLineItem[]
  payments: Payment[]
  returns?: unknown[]
}

/** Formatted folio string: "SERIES-0001" or last 8 chars of UUID */
export function saleLabel(s: Pick<SalesDocument, 'series' | 'folio' | 'id'>): string {
  if (s.series && s.folio != null) return `${s.series}-${String(s.folio).padStart(4, '0')}`
  return s.id.slice(-8).toUpperCase()
}

export interface CartItemPrice {
  id: string
  price_name: string
  min_quantity: number
  unit_price: number
  linked_package_id?: string | null  // tier vinculado a un PackagingUnit explícito
}

export interface CartItemPackaging {
  id: string
  name: string
  barcode: string | null
  units_per_package: number
  package_price: number
}

export interface CartItem {
  product_id: string
  variant_id?: string     // variante exacta (talla/color); el backend la prioriza sobre sku
  variant_label?: string  // "Rojo / M" para el carrito y el ticket en pantalla
  cart_key?: string      // clave única en el carrito; si ausente usa product_id
  base_price?: number    // precio unitario original, para restaurar al salir de modo caja
  unit_kind?: 'piece' | 'package'  // 'package' = item vendido por caja; inmune a re-evaluación de tiers pieza
  cajaForcedByBulk?: boolean       // marcado por applyCajaToAll; restoreAutoTier lo revierte a piezas
  sku: string
  name: string
  price: number
  quantity: number
  discount: number
  subtotal: number
  stock?: number         // stock disponible en sucursal (undefined = sin restricción)
  prices?: CartItemPrice[]
  packaging_units?: CartItemPackaging[]
  forcedPriceTier?: string | null  // tier forzado manualmente (nombre); se preserva en parked tickets
}
