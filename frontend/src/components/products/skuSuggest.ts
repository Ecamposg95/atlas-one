/**
 * Datos que alimentan la sugerencia de SKU (`GET /api/products/sku-suggest`).
 *
 * Funciones puras: el formulario tiene marca por ID y las tallas en la matriz,
 * y el endpoint quiere marca por NOMBRE y una sola combinación color/talla.
 * La convención (MARCA-PRENDA-MODELO-COLOR-TALLA) la resuelve el backend —
 * aquí solo se junta lo que hay en pantalla.
 */

export interface MarcaMinima {
  id: string
  name: string
}

export interface FilaVariante {
  color: string
  size: string
}

export interface ArgsSugerencia {
  name: string
  brand: string
  model: string
  color: string
  size: string
}

/** Nombre de la marca elegida; "" si no hay marca o el id ya no existe. */
export function nombreDeMarca(brands: MarcaMinima[], brandId: string | null | undefined): string {
  if (!brandId) return ''
  return brands.find((b) => b.id === brandId)?.name ?? ''
}

/**
 * Lo que se le manda al endpoint desde el formulario.
 *
 * El color y la talla salen de la PRIMERA fila de la matriz (la variante
 * principal, la que lleva el SKU base). Las hermanas no entran: sus SKU los
 * deriva la matriz del base con el sufijo de color/talla.
 */
export function argsSugerencia(
  form: { name: string; model?: string; brand_id?: string },
  brands: MarcaMinima[],
  filas: FilaVariante[] = [],
): ArgsSugerencia {
  const principal = filas[0]
  return {
    name: (form.name ?? '').trim(),
    brand: nombreDeMarca(brands, form.brand_id),
    model: (form.model ?? '').trim(),
    color: (principal?.color ?? '').trim(),
    size: (principal?.size ?? '').trim(),
  }
}

/**
 * Texto de la confirmación antes de pisar el SKU que el usuario ya escribió.
 *
 * Se pregunta SIEMPRE (la sugerencia nunca se aplica sola) y se avisa cuando
 * el código ya está ocupado: aceptarlo igual termina en un 409 al guardar.
 */
export function mensajeSugerencia(sku: string, disponible: boolean, skuActual: string): string {
  const cabeza = `SKU sugerido: ${sku}`
  const ocupado = disponible ? '' : '\n\nOJO: ese código ya lo tiene otra prenda de la tienda.'
  const pisa = skuActual.trim() && skuActual.trim() !== sku
    ? `\n\nReemplaza el que escribiste (${skuActual.trim()}).`
    : ''
  return `${cabeza}${ocupado}${pisa}\n\n¿Lo usamos?`
}
