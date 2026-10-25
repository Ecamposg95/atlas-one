// frontend/src/components/graficas/formato.ts

/** Moneda abreviada para ejes: "$950", "$1.2k", "$3.4M"; negativos con el signo delante ("-$1.2k"). */
export function dineroCorto(valor: number): string {
  const abs = Math.abs(valor)
  const signo = valor < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${signo}$${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${signo}$${(abs / 1_000).toFixed(1)}k`
  return `${signo}$${Math.round(abs)}`
}

/**
 * Ventana de horas a pintar (spec §2.1): de `min(9, primera hora con
 * movimiento)` a `max(21, última hora con movimiento)`. El backend manda las
 * 24; una venta a las 7 o una devolución a las 23 abren la ventana.
 */
export function recortarHoras(horas: { hora: number; neta: number }[]): { desde: number; hasta: number } {
  const conMovimiento = horas.filter((h) => h.neta !== 0).map((h) => h.hora)
  const desde = conMovimiento.length ? Math.min(9, ...conMovimiento) : 9
  const hasta = conMovimiento.length ? Math.max(21, ...conMovimiento) : 21
  return { desde, hasta }
}

export const etiquetaHora = (h: number): string => `${h}:00`
