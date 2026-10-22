import type { ProductoResumen } from '../../../api/conteos'
import type { Product, ProductVariant } from '../../../types/products'

/** Vibración corta al contar; triple cuando hay que mirar la pantalla. Sin API (PC) no hace nada. */
export function vibrar(tipo: 'ok' | 'aviso'): void {
  const v = (globalThis as { navigator?: { vibrate?: (p: number | number[]) => boolean } }).navigator?.vibrate
  if (typeof v !== 'function') return
  try { v.call(navigator, tipo === 'ok' ? 60 : [60, 60, 60]) } catch { /* Safari no vibra */ }
}

/** Lo que el buscador devuelve (producto + talla elegida) en la forma que usa la sesión. */
export function resumenDesdeProducto(p: Product, v: ProductVariant): ProductoResumen {
  return {
    variant_id: v.id,
    nombre: v.sale_name ?? p.sale_name ?? p.name,
    marca: p.brand_name ?? null,
    talla: v.size ?? null,
    color: v.color ?? null,
    sku: v.sku ?? null,
    barcode: v.barcode ?? null,
    foto: p.image_url ?? null,
    departamento: p.department_name ?? p.department?.name ?? null,
  }
}
