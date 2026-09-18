import type { Product, ProductVariant } from '../../types/products'

/** ¿Hay que preguntar talla/color antes de agregar al carrito? */
export function needsPicker(p: Product): boolean {
  const n = p.variants?.length ?? 0
  if (n <= 1) return false
  return !p.matched_variant_id
}

const txt = (v: string | null | undefined) => (v ?? '').trim()

/**
 * ¿El producto se distingue SOLO por talla?
 *
 * Una boutique de ropa sin colores capturados ve "variantes" por todos lados y
 * no significa nada: lo que tiene enfrente son tallas. Sirve para elegir el
 * vocabulario de la UI, no para decidir lógica de negocio.
 */
export function sizeOnly(vs: ProductVariant[]): boolean {
  if (!vs?.length) return false
  return vs.every((v) => !txt(v.color)) && vs.some((v) => !!txt(v.size))
}

/** "Talla(s)" cuando no hay colores; "Variante(s)" cuando sí. */
export function variantAxisLabel(vs: ProductVariant[], plural = false): string {
  const base = sizeOnly(vs) ? 'Talla' : 'Variante'
  return plural ? `${base}s` : base
}

/** El backend nombra "Estándar" a la variante sin atributos; el cajero espera el producto. */
const esEstandar = (nombre: string) => {
  const n = nombre.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
  return n === 'estandar'
}

/**
 * Nombre mostrable de una variante. NUNCA devuelve "Estándar": para la variante
 * única cae al nombre del producto, que es lo que el cajero reconoce.
 */
export function variantDisplayName(v: ProductVariant, productName: string): string {
  return variantShortLabel(v) ?? productName
}

/**
 * Etiqueta corta para badges y para la línea del carrito ("M", "Rojo / M"), o
 * `null` cuando la variante no distingue nada y no hay nada que etiquetar.
 */
export function variantShortLabel(v: ProductVariant): string | null {
  const nombre = txt(v.variant_name)
  if (nombre && !esEstandar(nombre)) return nombre
  const attrs = [txt(v.color), txt(v.size)].filter(Boolean).join(' / ')
  return attrs || null
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
