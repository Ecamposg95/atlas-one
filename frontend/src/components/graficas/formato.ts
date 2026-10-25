// frontend/src/components/graficas/formato.ts

/** Moneda abreviada para ejes: "$950", "$1.2k", "$3.4M"; negativos con el signo delante ("-$1.2k"). */
export function dineroCorto(valor: number): string {
  const abs = Math.abs(valor)
  // El umbral se mide ya redondeado: 999.5 es "$1.0k" (no "$1000") y 999 950 es "$1.0M" (no "$1000.0k").
  const entero = Math.round(abs)
  const signo = valor < 0 && entero > 0 ? '-' : ''   // -0.4 se pinta "$0", sin signo
  if (abs >= 999_950) return `${signo}$${(abs / 1_000_000).toFixed(1)}M`
  if (entero >= 1_000) return `${signo}$${(abs / 1_000).toFixed(1)}k`
  return `${signo}$${entero}`
}

/**
 * Ventana de horas a pintar (spec §2.1): de `min(9, primera hora con
 * movimiento)` a `max(21, última hora con movimiento)`. El backend manda las
 * 24; una venta a las 7 o una devolución a las 23 abren la ventana. Hay
 * movimiento con `neta ≠ 0` o con tickets (una venta cancelada a medias por una
 * devolución puede dejar la neta en 0 y el ticket sigue ahí).
 */
export function recortarHoras(horas: { hora: number; neta: number; tickets?: number }[]): { desde: number; hasta: number } {
  const conMovimiento = horas.filter((h) => h.neta !== 0 || (h.tickets ?? 0) > 0).map((h) => h.hora)
  const desde = conMovimiento.length ? Math.min(9, ...conMovimiento) : 9
  const hasta = conMovimiento.length ? Math.max(21, ...conMovimiento) : 21
  return { desde, hasta }
}

export const etiquetaHora = (h: number): string => `${h}:00`
