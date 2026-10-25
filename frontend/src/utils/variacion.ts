// frontend/src/utils/variacion.ts

/** Variación de una cifra contra su referencia (spec 2026-10-23 §3.1/§3.2). */
export interface Variacion {
  /** Porcentaje entero contra la referencia; null = sin referencia (anterior ≤ 0 con cifra ≠ 0). */
  pct: number | null
  /** "vs ayer", "vs antier", "vs semana anterior", "vs periodo anterior". */
  texto: string
  /** Subir es malo (devoluciones): invierte los colores. */
  invertida?: boolean
}

/**
 * Porcentaje entero de cambio. Con referencia cero o negativa no hay contra
 * qué comparar (no se divide entre cero ni se inventa "+100 %"): null. Cero
 * contra cero es "igual" (0).
 */
export function porcentajeVariacion(actual: number, anterior: number): number | null {
  if (anterior === 0 && actual === 0) return 0
  if (!(anterior > 0)) return null
  return Math.round(((actual - anterior) / anterior) * 100)
}

export function variacion(actual: number, anterior: number, texto: string, invertida = false): Variacion {
  return { pct: porcentajeVariacion(actual, anterior), texto, invertida }
}
