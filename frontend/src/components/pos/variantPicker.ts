import type { Product, ProductVariant } from '../../types/products'

/** ¿Hay que preguntar talla/color antes de agregar al carrito? */
export function needsPicker(p: Product): boolean {
  const n = p.variants?.length ?? 0
  if (n <= 1) return false
  return !p.matched_variant_id
}

export function groupVariants(vs: ProductVariant[]) {
  const colors: string[] = []
  const sizes: string[] = []
  const idx = new Map<string, ProductVariant>()
  const k = (c: string, s: string) => `${c.toLowerCase()}|${s.toLowerCase()}`
  for (const v of vs) {
    const c = v.color ?? ''
    const s = v.size ?? ''
    if (!colors.some((x) => x.toLowerCase() === c.toLowerCase())) colors.push(c)
    if (!sizes.some((x) => x.toLowerCase() === s.toLowerCase())) sizes.push(s)
    idx.set(k(c, s), v)
  }
  return { colors, sizes, at: (c: string, s: string) => idx.get(k(c, s)) }
}

/** Producto con los campos aplanados de la variante elegida (lo que consume addToCart). */
export function pickVariantForCart(p: Product, v: ProductVariant): Product {
  return {
    ...p,
    matched_variant_id: v.id,
    sku: v.sku,
    barcode: v.barcode ?? null,
    price: Number(v.price),
    stock_total: Number(v.stock_total ?? 0),
    prices: v.prices ?? p.prices,
    packaging_units: v.packaging_units ?? p.packaging_units,
  }
}
