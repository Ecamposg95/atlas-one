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
      const nombre = nombreDeVariante(p, v)
      const conNombre = vs.length > 1 && nombre !== p.name
      rows.push({
        product: p, variant: v,
        label: conNombre ? `${p.name} · ${nombre}` : p.name,
        sku: v.sku, barcode: v.barcode ?? null, qty: Number(v.stock_total ?? 0),
      })
    }
  }
  return rows
}

/**
 * Cómo se llama UNA variante en pantalla.
 *
 * "Estándar" es el nombre que el backend le pone a la variante única de un
 * producto sin atributos: es jerga interna y al dueño no le dice nada, así
 * que en su lugar se muestra el nombre del producto.
 */
export function nombreDeVariante(product: Product, variant: ProductVariant): string {
  const nombre = (variant.variant_name ?? '').trim()
  if (!nombre || nombre === 'Estándar') return product.name
  return nombre
}

/**
 * Cómo llamarle al conjunto de variantes en la UI.
 *
 * La boutique que motivó esto vende tallas y no usa colores: decirle
 * "variantes" a Ch/M/G no le dice nada. Si ninguna variante tiene color,
 * hablamos de "tallas"; si ninguna tiene talla, de "colores"; y solo cuando
 * se mezclan (o no hay atributos) caemos en el genérico "variantes".
 */
export function grupoDeVariantes(variants: ProductVariant[]): 'tallas' | 'colores' | 'variantes' {
  const hayColor = variants.some((v) => (v.color ?? '').trim() !== '')
  const hayTalla = variants.some((v) => (v.size ?? '').trim() !== '')
  if (hayTalla && !hayColor) return 'tallas'
  if (hayColor && !hayTalla) return 'colores'
  return 'variantes'
}

/**
 * Existencia del producto sumando TODAS sus tallas.
 *
 * El catálogo mostraba `stock_total`, que es el aplanado de la variante
 * principal: una boutique con 3 en Ch, 7 en M y 2 en G leía "3" y creía que
 * se estaba quedando sin mercancía.
 */
export function sumStock(product: Product): number {
  const vs = product.variants ?? []
  if (vs.length === 0) return Number(product.stock_total ?? product.stock ?? 0)
  return vs.reduce((acc, v) => acc + Number(v.stock_total ?? 0), 0)
}

export interface RangoPrecio {
  min: number
  max: number
  /** true cuando todas las tallas cuestan lo mismo (se muestra un solo precio). */
  uniforme: boolean
}

/** Rango de precios entre las variantes; null si el producto no tiene ninguna. */
export function priceRange(variants: ProductVariant[]): RangoPrecio | null {
  if (variants.length === 0) return null
  const precios = variants.map((v) => Number(v.price ?? 0))
  const min = Math.min(...precios)
  const max = Math.max(...precios)
  return { min, max, uniforme: min === max }
}
