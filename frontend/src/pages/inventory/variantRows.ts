import { esEstandar } from '../../components/pos/variantPicker'
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
 * que en su lugar se muestra el nombre del producto. La comparación va por
 * `esEstandar` (sin acentos y en minúsculas): el nombre llega escrito de
 * varias formas según quién sembró la variante, y comparar contra el literal
 * "Estándar" dejaba "estandar" colándose al inventario como nombre de fila.
 */
export function nombreDeVariante(product: Product, variant: ProductVariant): string {
  const nombre = (variant.variant_name ?? '').trim()
  if (!nombre || esEstandar(nombre)) return product.name
  return nombre
}

/**
 * Qué buscar al entrar a Inventario desde otra pantalla.
 *
 * El editor de variantes enlaza a `/inventory?variant=<id>&q=<sku>` con el
 * botón "Ajustar", pero la pantalla no leía nada: el admin aterrizaba en un
 * buscador vacío y tenía que teclear el SKU que acababa de ver. Devuelve el
 * texto a sembrar y la variante a abrir (el kardex de ESA talla, no el de la
 * primera).
 */
export function initialInventoryQuery(search: string): { q: string; variant: string | null } {
  const params = new URLSearchParams((search ?? '').replace(/^\?/, ''))
  const q = (params.get('q') ?? '').trim()
  const variant = (params.get('variant') ?? '').trim()
  return { q, variant: variant || null }
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
