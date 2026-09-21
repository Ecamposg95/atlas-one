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
 * Lo que se le manda al endpoint desde el formulario: marca, nombre y modelo.
 *
 * **Sin color ni talla, a propósito.** El SKU que se sugiere es el de la
 * FAMILIA (`LV-CHAM-MEZ`): la matriz de tallas le pega a cada hermana su
 * propio sufijo (`LV-CHAM-MEZ-BEIGE-M`, `-BEIGE-CH`…) en `buildVariantRows`.
 * Si le pegáramos además la primera talla, el base nacería como
 * `LV-CHAM-MEZ-BEI-CH` y las hermanas quedarían
 * `LV-CHAM-MEZ-BEI-CH-BEIGE-M`.
 *
 * El endpoint sí acepta `color`/`size` (los usa quien sugiera el SKU de UNA
 * variante suelta); este formulario no los manda nunca.
 */
export function argsSugerencia(
  form: { name: string; model?: string; brand_id?: string },
  brands: MarcaMinima[],
): ArgsSugerencia {
  return {
    name: (form.name ?? '').trim(),
    brand: nombreDeMarca(brands, form.brand_id),
    model: (form.model ?? '').trim(),
    color: '',
    size: '',
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
