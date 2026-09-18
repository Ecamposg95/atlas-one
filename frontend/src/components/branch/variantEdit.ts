import type { Product } from '../../types/products'

/**
 * El catálogo de sucursal pinta un renglón por talla, pero "Editar" abría
 * siempre el formulario del PRODUCTO, y `PUT /products/{id}` escribe el SKU y
 * el código de barras de la variante PRINCIPAL. Editar la fila de M terminaba
 * renombrando el SKU de Ch (o chocando con un 409 por duplicado).
 *
 * Estos helpers deciden a dónde va la identidad de cada renglón: la fila
 * principal sigue por el producto (comportamiento de siempre) y las demás
 * tallas se rutean a `PUT /products/variants/{id}`.
 */

/** ¿El renglón representa la variante principal (la primera viva) o el producto entero? */
export function esFilaPrincipal(product: Product, variantId: string | undefined): boolean {
  const vivas = product.variants ?? []
  if (vivas.length === 0 || !variantId) return true
  // Un id que ya no está (talla retirada entre el listado y el guardado) se
  // trata como principal: es a lo que apunta el formulario que se ve.
  if (!vivas.some((v) => v.id === variantId)) return true
  return vivas[0].id === variantId
}

export interface IdentidadDeFila {
  esPrincipal: boolean
  /** Campos de identidad para `PUT /products/{id}` — vacío si la fila no es la principal. */
  productPatch: { sku?: string; barcode?: string | null }
  /** Campos para `PUT /products/variants/{id}` — null si no hay nada que cambiar. */
  variantPatch: { variantId: string; patch: { sku?: string; barcode?: string | null } } | null
}

export function planIdentidadDeFila(
  product: Product,
  variantId: string | undefined,
  entrada: { sku: string; barcode: string | null },
): IdentidadDeFila {
  const barcode = (entrada.barcode ?? '').trim() || null

  if (esFilaPrincipal(product, variantId)) {
    return { esPrincipal: true, productPatch: { sku: entrada.sku, barcode }, variantPatch: null }
  }

  const v = (product.variants ?? []).find((x) => x.id === variantId)!
  const patch: { sku?: string; barcode?: string | null } = {}
  if (entrada.sku !== v.sku) patch.sku = entrada.sku
  if (barcode !== ((v.barcode ?? '').trim() || null)) patch.barcode = barcode

  return {
    esPrincipal: false,
    productPatch: {},
    variantPatch: Object.keys(patch).length > 0 ? { variantId: v.id, patch } : null,
  }
}
