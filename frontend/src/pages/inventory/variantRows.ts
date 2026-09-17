import type { Product, ProductVariant } from '../../types/products'

export interface InventoryRow {
  product: Product
  variant: ProductVariant
  label: string
  sku: string
  barcode: string | null
  qty: number
}

/**
 * Un renglón de inventario por variante. Antes las pantallas tomaban
 * `variants[0]` y con varias tallas el kardex y los ajustes iban a la primera.
 */
export function expandVariantRows(products: Product[]): InventoryRow[] {
  const rows: InventoryRow[] = []
  for (const p of products) {
    const vs = p.variants ?? []
    if (vs.length === 0) {
      rows.push({
        product: p,
        variant: { id: p.id, product_id: p.id, sku: p.sku, price: p.price, cost: p.cost, variant_name: 'Estándar' },
        label: p.name, sku: p.sku, barcode: p.barcode ?? null, qty: Number(p.stock_total ?? 0),
      })
      continue
    }
    for (const v of vs) {
      const conNombre = vs.length > 1 && v.variant_name && v.variant_name !== 'Estándar'
      rows.push({
        product: p, variant: v,
        label: conNombre ? `${p.name} · ${v.variant_name}` : p.name,
        sku: v.sku, barcode: v.barcode ?? null, qty: Number(v.stock_total ?? 0),
      })
    }
  }
  return rows
}
