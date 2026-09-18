/**
 * Vocabulario de variantes (hallazgo #19 de la auditoría UI/UX).
 *
 * Una boutique de tallas Ch/M/G no tiene colores: hablarle de "variantes" o
 * pintarle una columna "Color" vacía sobra. Y "Estándar" —el nombre que el
 * backend le pone a la variante única de un producto sin color ni talla— no
 * significa nada para quien atiende el mostrador: ahí va el nombre del
 * producto.
 *
 * Funciones puras: quien pinta decide, aquí solo se elige la palabra.
 */

export interface VariantLike {
  variant_name?: string | null
  color?: string | null
  size?: string | null
}

/** ¿Alguna variante tiene color? Si no, la org solo maneja tallas. */
export function usesColors(variants: VariantLike[] | null | undefined): boolean {
  return (variants ?? []).some((v) => Boolean((v.color ?? '').trim()))
}

/**
 * Cómo llamar a las variantes en pantalla. Con colores son "variantes"; sin
 * colores, "tallas" — que es como lo dice la dueña de la tienda.
 */
export function variantWords(conColores: boolean): { singular: string; plural: string } {
  return conColores
    ? { singular: 'variante', plural: 'variantes' }
    : { singular: 'talla', plural: 'tallas' }
}

/**
 * Etiqueta de una variante. Nunca devuelve "Estándar": una variante sin color
 * ni talla ES el producto, así que se muestra con su nombre.
 */
export function variantLabel(v: VariantLike | null | undefined, productName: string): string {
  const atributos = [v?.color, v?.size].map((x) => (x ?? '').trim()).filter(Boolean)
  if (atributos.length > 0) return atributos.join(' / ')
  const nombre = (v?.variant_name ?? '').trim()
  if (nombre && nombre.toLowerCase() !== 'estándar' && nombre.toLowerCase() !== 'estandar') return nombre
  return productName.trim() || 'Producto'
}
