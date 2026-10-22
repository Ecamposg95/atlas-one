import type { Reporte } from '../../../api/conteos'

/** Decimal del backend ("3.00") a número; vacío o basura = 0. */
export function num(v: string | number | null | undefined): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** Porcentaje entero 0-100 de variantes contadas sobre esperadas. */
export function porcentajeAvance(contadas: number, esperadas: number): number {
  if (esperadas <= 0) return 0
  return Math.min(100, Math.round((contadas / esperadas) * 100))
}

/** "faltan 3" / "falta 1" / "sobra 1" / "sobran 2" / "cuadra". */
export function textoDiferencia(diferencia: number): string {
  if (diferencia === 0) return 'cuadra'
  const n = Math.abs(diferencia)
  if (diferencia < 0) return n === 1 ? 'falta 1' : `faltan ${n}`
  return n === 1 ? 'sobra 1' : `sobran ${n}`
}

export interface Seccion {
  clave: 'faltantes' | 'sobrantes' | 'fuera_de_alcance' | 'desconocidos'
  titulo: string
  filas: number
  piezas: number
}

/** Las cuatro secciones del reporte en el orden en que se leen. */
export function seccionesReporte(r: Reporte): Seccion[] {
  return [
    { clave: 'faltantes', titulo: 'Faltantes', filas: r.faltantes.length, piezas: num(r.totales.faltantes_piezas) },
    { clave: 'sobrantes', titulo: 'Sobrantes', filas: r.sobrantes.length, piezas: num(r.totales.sobrantes_piezas) },
    { clave: 'fuera_de_alcance', titulo: 'Fuera de departamento', filas: r.fuera_de_alcance.length, piezas: num(r.totales.fuera_de_alcance_piezas) },
    { clave: 'desconocidos', titulo: 'Desconocidos', filas: r.desconocidos.length, piezas: r.desconocidos.reduce((s, d) => s + num(d.contado), 0) },
  ]
}
