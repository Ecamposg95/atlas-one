/**
 * Filtros avanzados de la lista de Productos (`/products`): género, talla,
 * color, solo con existencia y fecha de alta. Los mismos ejes que Etiquetas,
 * pero aquí la lista es PAGINADA: todo viaja al servidor como query params de
 * `GET /api/products/` (y de las cifras y el Excel), que filtra antes de paginar.
 *
 * Funciones puras, sin React ni red (`filtrosAvanzadosProductos.test.ts`).
 */

export interface FiltrosAvanzados {
  /** HOMBRE | MUJER | UNISEX | NINO; vacío = todos. */
  gender: string
  /** Talla exacta de una variante; vacío = todas. */
  size: string
  /** Color exacto de una variante; vacío = todos. */
  color: string
  only_with_stock: boolean
  /** `YYYY-MM-DD` local (input date); vacío = sin filtro. */
  created_after: string
}

export const AVANZADOS_VACIOS: FiltrosAvanzados = {
  gender: '',
  size: '',
  color: '',
  only_with_stock: false,
  created_after: '',
}

/** Cuántos ejes avanzados están puestos (el contador del botón «Más filtros»). */
export function contarAvanzados(f: FiltrosAvanzados): number {
  return [f.gender, f.size, f.color, f.created_after].filter((v) => v !== '').length + (f.only_with_stock ? 1 : 0)
}

export const hayAvanzados = (f: FiltrosAvanzados): boolean => contarAvanzados(f) > 0

/**
 * Medianoche LOCAL del día elegido, en ISO (UTC). «Dados de alta desde el 3»
 * es desde que empezó el 3 en la tienda, no desde las 00:00 de Greenwich.
 * Una fecha mal formada no filtra (devuelve `null`).
 */
export function inicioDelDiaIso(fecha: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(fecha.trim())
  if (!m) return null
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 0, 0, 0, 0)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

/** Fecha local de hoy como la escribe el input date (`YYYY-MM-DD`). */
export function hoyLocal(ahora: Date = new Date()): string {
  const dos = (n: number) => String(n).padStart(2, '0')
  return `${ahora.getFullYear()}-${dos(ahora.getMonth() + 1)}-${dos(ahora.getDate())}`
}

/** Query params de los ejes puestos; los vacíos no viajan. */
export function paramsAvanzados(f: FiltrosAvanzados): {
  gender?: string
  size?: string
  color?: string
  only_with_stock?: boolean
  created_after?: string
} {
  const p: ReturnType<typeof paramsAvanzados> = {}
  if (f.gender) p.gender = f.gender
  if (f.size.trim()) p.size = f.size.trim()
  if (f.color.trim()) p.color = f.color.trim()
  if (f.only_with_stock) p.only_with_stock = true
  const desde = f.created_after ? inicioDelDiaIso(f.created_after) : null
  if (desde) p.created_after = desde
  return p
}
